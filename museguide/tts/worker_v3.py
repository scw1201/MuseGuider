# museguide/tts/worker_v3.py
import asyncio
import gzip
import json
import logging
import os
import struct
import uuid
from pathlib import Path
from typing import Optional, Tuple

import websockets
import yaml

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tts.worker_v3")

ENDPOINT_V3 = "wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream"

# Protocol bits
PROTO_VER = 0b0001
HEADER_SIZE = 0b0001  # 4 bytes

MSG_FULL_REQ = 0b0001
MSG_FULL_RESP = 0b1001
MSG_AUDIO_RESP = 0b1011
MSG_ERROR = 0b1111

FLAG_NONE = 0b0000
FLAG_WITH_EVENT = 0b0100

SER_RAW = 0b0000
SER_JSON = 0b0001

COMP_NONE = 0b0000
COMP_GZIP = 0b0001

EVENT_FINISH_CONN = 2
EVENT_TTS_RESPONSE = 352
EVENT_SESSION_FINISHED = 152


def _make_header(msg_type: int, flags: int, serialization: int, compression: int) -> bytes:
    b0 = (PROTO_VER << 4) | HEADER_SIZE
    b1 = (msg_type << 4) | flags
    b2 = (serialization << 4) | compression
    b3 = 0x00
    return bytes([b0, b1, b2, b3])


def _make_request_frame(payload_json: dict) -> bytes:
    payload = json.dumps(payload_json, ensure_ascii=False).encode("utf-8")
    header = _make_header(MSG_FULL_REQ, FLAG_NONE, SER_JSON, COMP_NONE)
    return header + len(payload).to_bytes(4, "big") + payload


def _make_finish_frame() -> bytes:
    payload = b"{}"
    header = _make_header(MSG_FULL_REQ, FLAG_WITH_EVENT, SER_JSON, COMP_NONE)
    return header + EVENT_FINISH_CONN.to_bytes(4, "big") + len(payload).to_bytes(4, "big") + payload


def _parse_frame(data: bytes) -> Tuple[int, int, bytes, int, int]:
    if len(data) < 4:
        raise ValueError("frame too short")

    header_bytes = (data[0] & 0x0F) * 4
    msg_type = data[1] >> 4
    flags = data[1] & 0x0F
    serialization = data[2] >> 4
    compression = data[2] & 0x0F

    offset = header_bytes
    event = 0
    if flags == FLAG_WITH_EVENT:
        event = int.from_bytes(data[offset:offset + 4], "big")
        offset += 4

    if msg_type == MSG_ERROR:
        code = int.from_bytes(data[offset:offset + 4], "big")
        msg = data[offset + 4 :]
        if compression == COMP_GZIP:
            try:
                msg = gzip.decompress(msg)
            except Exception:
                pass
        return event, msg_type, msg, serialization, compression

    if offset + 4 > len(data):
        return event, msg_type, b"", serialization, compression

    sid_len = int.from_bytes(data[offset:offset + 4], "big")
    offset += 4 + sid_len

    if offset + 4 > len(data):
        return event, msg_type, b"", serialization, compression

    payload_len = int.from_bytes(data[offset:offset + 4], "big")
    offset += 4
    payload = data[offset:offset + payload_len]

    if compression == COMP_GZIP:
        try:
            payload = gzip.decompress(payload)
        except Exception:
            pass

    return event, msg_type, payload, serialization, compression


def _load_secrets() -> dict:
    path = Path(__file__).parents[1] / "configs" / "secrets.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class TTSV3Session:
    def __init__(self):
        secrets = _load_secrets()
        tts_cfg = secrets.get("tts", {})
        self.appid = tts_cfg.get("appid")
        self.access_key = tts_cfg.get("access_token")
        self.resource_id = tts_cfg.get("resource_id") or "seed-tts-1.0"
        self.voice_type = tts_cfg.get("voice_type", "zh_female_cancan_mars_bigtts")
        self.format = tts_cfg.get("audio_format", "pcm")
        self.sample_rate = int(tts_cfg.get("sample_rate", 24000))
        self.endpoint = tts_cfg.get("endpoint_v3", ENDPOINT_V3)

        if not self.appid or not self.access_key:
            raise RuntimeError("TTS_APPID / TTS_ACCESS_TOKEN 未设置")

        self._ws: Optional[object] = None
        self._lock = asyncio.Lock()

    def _ws_dead(self) -> bool:
        if self._ws is None:
            return True
        try:
            return getattr(self._ws, "close_code", None) is not None
        except Exception:
            return True

    async def _connect(self):
        headers = {
            "X-Api-App-Id": self.appid,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        logger.info(f"Connecting to TTS v3 WS: {self.endpoint}")
        self._ws = await websockets.connect(
            self.endpoint,
            extra_headers=headers,
            max_size=20 * 1024 * 1024,
        )
        logid = None
        try:
            logid = self._ws.response.headers.get("x-tt-logid")
        except Exception:
            pass
        logger.info(f"TTS v3 WS connected. Logid={logid}")

    async def _ensure_ws(self):
        if self._ws_dead():
            await self._connect()

    async def synthesize_stream(self, text: str, client_ws, voice_type: Optional[str] = None) -> float:
        if not isinstance(text, str):
            text = str(text)
        text = text.strip()
        if not text:
            raise ValueError("Empty text for TTS")
        if len(text) > 300:
            text = text[:300]

        async with self._lock:
            await self._ensure_ws()
            use_voice_type = voice_type or self.voice_type

            req = {
                "user": {"uid": "museguide"},
                "req_params": {
                    "text": text,
                    "speaker": use_voice_type,
                    "audio_params": {
                        "format": self.format,
                        "sample_rate": self.sample_rate,
                    },
                },
            }

            await self._ws.send(_make_request_frame(req))

            # send meta to browser
            await client_ws.send(
                json.dumps(
                    {
                        "type": "meta",
                        "format": "pcm_s16le",
                        "sample_rate": self.sample_rate,
                        "channels": 1,
                    },
                    ensure_ascii=False,
                )
            )

            while True:
                msg = await self._ws.recv()
                if not isinstance(msg, (bytes, bytearray)):
                    continue

                event, msg_type, payload, serialization, _ = _parse_frame(msg)

                if msg_type == MSG_ERROR:
                    raise RuntimeError(f"TTS v3 error: {payload!r}")

                if event == EVENT_TTS_RESPONSE and msg_type == MSG_AUDIO_RESP:
                    # raw PCM bytes
                    await client_ws.send(payload)
                    continue

                if event == EVENT_SESSION_FINISHED:
                    return 0.0

                # For text events, ignore for now.
                if serialization == SER_JSON and payload:
                    try:
                        _ = json.loads(payload.decode("utf-8"))
                    except Exception:
                        pass

    async def close(self):
        try:
            if self._ws is not None:
                await self._ws.send(_make_finish_frame())
                await self._ws.close()
        except Exception:
            pass
        self._ws = None


async def ws_handler(client_ws, session: TTSV3Session):
    logger.info("Client connected (browser ws)")
    try:
        async for msg in client_ws:
            if isinstance(msg, (bytes, bytearray)):
                continue
            req = json.loads(msg)
            text = req.get("text", "")
            voice_type = req.get("voice_type")

            await client_ws.send(json.dumps({"type": "start"}, ensure_ascii=False))
            await session.synthesize_stream(
                text=text,
                client_ws=client_ws,
                voice_type=voice_type,
            )
            await client_ws.send(json.dumps({"type": "end"}, ensure_ascii=False))

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

    session = TTSV3Session()
    await session._ensure_ws()

    logger.info(f"TTS v3 Browser-WS listening on ws://{host}:{port}")
    async with websockets.serve(lambda ws: ws_handler(ws, session), host, port, max_size=20 * 1024 * 1024):
        try:
            await asyncio.Future()
        finally:
            await session.close()


if __name__ == "__main__":
    asyncio.run(main())
