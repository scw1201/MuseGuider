# musetalker/tts/worker.py
import asyncio
import json
import logging
import os
import struct
import time
import uuid
from pathlib import Path
import yaml
from typing import Optional, Tuple

import websockets
import sys

# 🔥 强制把 volcengine_binary_demo 加进 PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parents[2]
VOLC_DIR = PROJECT_ROOT / "volcengine_binary_demo"
if not VOLC_DIR.exists():
    raise RuntimeError(f"volcengine_binary_demo not found: {VOLC_DIR}")
sys.path.insert(0, str(VOLC_DIR))

from protocols.protocols import MsgType, full_client_request, receive_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tts.worker")


def _get_cluster(voice_type: str) -> str:
    return "volcano_icl" if voice_type.startswith("S_") else "volcano_tts"


def _parse_wav_header(buf: bytes) -> Tuple[int, int, int]:
    """
    返回 (data_offset, sample_rate, channels)
    只处理最常见 RIFF/WAVE + fmt + data 结构
    """
    if len(buf) < 44 or buf[0:4] != b"RIFF" or buf[8:12] != b"WAVE":
        raise ValueError("Not a WAV stream (missing RIFF/WAVE)")

    offset = 12
    sample_rate = None
    channels = None
    data_offset = None

    while offset + 8 <= len(buf):
        chunk_id = buf[offset:offset + 4]
        chunk_size = struct.unpack("<I", buf[offset + 4:offset + 8])[0]
        chunk_data_start = offset + 8
        chunk_data_end = chunk_data_start + chunk_size

        if chunk_id == b"fmt ":
            if chunk_size < 16:
                raise ValueError("Invalid fmt chunk")
            audio_format, ch, sr = struct.unpack("<HHI", buf[chunk_data_start:chunk_data_start + 8])
            channels = ch
            sample_rate = sr

        if chunk_id == b"data":
            data_offset = chunk_data_start
            break

        offset = chunk_data_end + (chunk_size % 2)
        if offset > len(buf):
            break

    if sample_rate is None or channels is None or data_offset is None:
        raise ValueError("Failed to parse WAV header (fmt/data not found yet)")

    return data_offset, sample_rate, channels


def _load_secrets() -> dict:
    path = Path(__file__).parents[1] / "configs" / "secrets.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class TTSSession:
    def __init__(self):
        secrets = _load_secrets()
        tts_cfg = secrets.get("tts", {})
        self.appid = tts_cfg.get("appid")
        self.access_token = tts_cfg.get("access_token")
        self.voice_type = tts_cfg.get("voice_type", "zh_female_cancan_mars_bigtts")
        self.encoding = tts_cfg.get("encoding", "wav")
        self.endpoint = tts_cfg.get("endpoint_v1", "wss://openspeech.bytedance.com/api/v1/tts/ws_binary")

        if not self.appid or not self.access_token:
            raise RuntimeError("TTS_APPID / TTS_ACCESS_TOKEN 未设置")

        self._ws: Optional[object] = None
        self._lock = asyncio.Lock()

    def _ws_dead(self) -> bool:
        # websockets 新版本不一定有 .closed，用 close_code 判断更稳
        if self._ws is None:
            return True
        try:
            return getattr(self._ws, "close_code", None) is not None
        except Exception:
            return True

    async def _connect(self):
        headers = {"Authorization": f"Bearer;{self.access_token}"}
        logger.info(f"Connecting to TTS WS: {self.endpoint}")
        self._ws = await websockets.connect(
            self.endpoint,
            extra_headers=headers,
            max_size=10 * 1024 * 1024,
        )
        logid = None
        try:
            logid = self._ws.response.headers.get("x-tt-logid")
        except Exception:
            pass
        logger.info(f"TTS WS connected. Logid={logid}")

    async def _ensure_ws(self):
        if self._ws_dead():
            await self._connect()

    async def synthesize_stream(
        self, text: str, client_ws, voice_type: Optional[str] = None
    ) -> float:
        """
        对外（浏览器 WS）流式输出：
        - 先发 meta（text frame JSON）
        - 再发 binary frame：PCM s16le bytes
        """
        if not isinstance(text, str):
            text = str(text)
        text = text.strip()
        if not text:
            raise ValueError("Empty text for TTS")
        if len(text) > 300:
            text = text[:300]

        async with self._lock:
            t0 = time.perf_counter()
            await self._ensure_ws()

            use_voice_type = voice_type or self.voice_type
            cluster = _get_cluster(use_voice_type)
            req = {
                "app": {"appid": self.appid, "token": self.access_token, "cluster": cluster},
                "user": {"uid": str(uuid.uuid4())},
                "audio": {"voice_type": use_voice_type, "encoding": self.encoding},
                "request": {
                    "reqid": str(uuid.uuid4()),
                    "text": text,
                    "operation": "submit",
                    "with_timestamp": "1",
                    "extra_param": json.dumps({"disable_markdown_filter": False}),
                },
            }

            await full_client_request(self._ws, json.dumps(req).encode("utf-8"))

            header_buf = bytearray()
            header_parsed = False
            data_offset = 0
            sample_rate = 0
            channels = 0

            try:
                while True:
                    msg = await receive_message(self._ws)

                    if msg.type == MsgType.FrontEndResultServer:
                        continue

                    if msg.type != MsgType.AudioOnlyServer:
                        raise RuntimeError(f"TTS failed: {msg}")

                    payload = msg.payload or b""
                    if payload:
                        if not header_parsed:
                            header_buf.extend(payload)
                            try:
                                data_offset, sample_rate, channels = _parse_wav_header(bytes(header_buf))
                                header_parsed = True

                                # 1) meta -> text frame
                                await client_ws.send(json.dumps({
                                    "type": "meta",
                                    "format": "pcm_s16le",
                                    "sample_rate": sample_rate,
                                    "channels": channels,
                                }, ensure_ascii=False))

                                # 2) header 后面的 PCM 立刻吐出去 -> binary frame
                                pcm0 = bytes(header_buf[data_offset:])
                                if pcm0:
                                    await client_ws.send(pcm0)

                                header_buf.clear()
                            except Exception:
                                pass
                        else:
                            # 已解析，直接发 PCM bytes
                            await client_ws.send(payload)

                    if msg.sequence < 0:
                        break

            except Exception as e:
                logger.error(f"TTS stream error: {e}. Reset tts ws.")
                try:
                    if self._ws is not None:
                        await self._ws.close()
                except Exception:
                    pass
                self._ws = None
                raise

            return (time.perf_counter() - t0) * 1000.0

    async def close(self):
        try:
            if self._ws is not None:
                await self._ws.close()
        except Exception:
            pass
        self._ws = None


async def ws_handler(client_ws, session: TTSSession):
    """
    浏览器协议：
    - 客户端发：{"text":"..."}
    - 服务端先发 text meta：{"type":"meta", ...}
    - 服务端持续发 binary：PCM s16le bytes
    - 结束再发 text end：{"type":"end", "latency_ms": ...}
    """
    logger.info("Client connected (browser ws)")
    try:
        async for msg in client_ws:
            if isinstance(msg, (bytes, bytearray)):
                continue
            req = json.loads(msg)
            text = req.get("text", "")
            voice_type = req.get("voice_type")

            await client_ws.send(json.dumps({"type": "start"}, ensure_ascii=False))
            latency_ms = await session.synthesize_stream(
                text=text,
                client_ws=client_ws,
                voice_type=voice_type,
            )
            await client_ws.send(json.dumps({"type": "end", "latency_ms": latency_ms}, ensure_ascii=False))

    except Exception as e:
        try:
            await client_ws.send(json.dumps({"type": "error", "error": str(e)}, ensure_ascii=False))
        except Exception:
            pass
    finally:
        logger.info("Client disconnected")


async def main():
    host = os.getenv("TTS_WORKER_HOST", "127.0.0.1")
    port = int(os.getenv("TTS_WORKER_PORT", "8765"))

    session = TTSSession()
    await session._ensure_ws()

    logger.info(f"TTS Browser-WS listening on ws://{host}:{port}")
    async with websockets.serve(lambda ws: ws_handler(ws, session), host, port, max_size=20 * 1024 * 1024):
        try:
            await asyncio.Future()
        finally:
            await session.close()


if __name__ == "__main__":
    asyncio.run(main())
