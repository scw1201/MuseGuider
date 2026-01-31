# museguide/asr/v3_bigmodel_client.py
import asyncio
import gzip
import json
import uuid
import yaml
import websockets
import struct

WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"


def load_config():
    with open("museguide/configs/secrets.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("asr", {})


def parse_server_frame(frame: bytes):
    """
    解析火山 ASR Server Frame
    返回 dict 或 None
    """
    if not isinstance(frame, (bytes, bytearray)):
        print("⚠️ [ASR] non-bytes frame:", type(frame))
        return None

    if len(frame) < 12:
        print("⚠️ [ASR] frame too short:", len(frame))
        return None

    b0, b1, b2, b3 = frame[:4]

    msg_type = (b1 >> 4) & 0x0F
    flags = b1 & 0x0F
    compression = b2 & 0x0F

    print(f"🧠 [ASR] frame type={msg_type} flags={flags} comp={compression}")

    # 这里对你的协议实现：4~8 seq，8~12 payload_len，12~ payload
    seq = struct.unpack(">I", frame[4:8])[0]
    payload_len = struct.unpack(">I", frame[8:12])[0]
    payload = frame[12:12 + payload_len]

    if compression == 1:
        try:
            payload = gzip.decompress(payload)
        except Exception as e:
            print("❌ [ASR] gzip decompress failed:", e)
            return None

    try:
        data = json.loads(payload.decode("utf-8"))
        return data
    except Exception as e:
        print("❌ [ASR] json parse failed:", e)
        print("RAW payload head:", payload[:200])
        return None


class BigModelASR:
    def __init__(self):
        cfg = load_config()
        self.app_id = cfg.get("app_id")
        self.access_token = cfg.get("access_token")
        self.resource_id = cfg.get("resource_id")

        self.ws: websockets.WebSocketClientProtocol | None = None
        self.conn_id = str(uuid.uuid4())
        self.connected = False

    async def connect_once(self):
        if self.connected and self.ws and not self.ws.closed:
            return

        print("🔌 [ASR] connecting once...")

        headers = {
            "X-Api-App-Key": self.app_id,
            "X-Api-Access-Key": self.access_token,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Connect-Id": self.conn_id,
        }

        self.ws = await websockets.connect(
            WS_URL,
            extra_headers=headers,
            max_size=10 * 1024 * 1024,
        )

        # ===== Full Client Request =====
        req = {
            "user": {"uid": "museguide"},
            "audio": {
                "format": "pcm",
                "rate": 16000,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "result_type": "single",
                "enable_punc": False,
                "enable_itn": False,
            },
        }

        payload = gzip.compress(json.dumps(req).encode("utf-8"))
        header = bytes([0x11, 0x10, 0x11, 0x00])
        msg = header + len(payload).to_bytes(4, "big") + payload

        await self.ws.send(msg)
        ack = await self.ws.recv()
        print("🧠 [ASR] full request ACK len:", len(ack))

        self.connected = True
        print("✅ [ASR] connected")

    async def send_audio(self, pcm: bytes, is_last: bool = False) -> str | None:
        """
        发送一段 pcm，并在短时间窗口内 drain 掉服务器回包
        返回“最新一次拿到的 text”，没有就 None
        """
        await self.connect_once()
        assert self.ws is not None

        payload = gzip.compress(pcm)
        flags = 0x02 if is_last else 0x00
        header = bytes([0x11, 0x20 | flags, 0x01, 0x00])
        msg = header + len(payload).to_bytes(4, "big") + payload

        print(f"➡️ [ASR] send audio len={len(pcm)} is_last={is_last}")
        await self.ws.send(msg)

        final_text: str | None = None

        # STOP 的时候多等一会儿把尾巴拿干净
        drain_timeout = 0.8 if is_last else 0.05
        per_recv_timeout = 0.05 if is_last else 0.02

        deadline = asyncio.get_event_loop().time() + drain_timeout

        while True:
            now = asyncio.get_event_loop().time()
            if now >= deadline:
                break

            try:
                resp = await asyncio.wait_for(self.ws.recv(), timeout=per_recv_timeout)
            except asyncio.TimeoutError:
                # 没新帧就继续等到 deadline
                continue
            except websockets.exceptions.ConnectionClosed as e:
                print("⚠️ [ASR] ws closed while recv:", e)
                break

            data = parse_server_frame(resp)
            if not data:
                continue

            # 错误直接打出来
            if "error" in data:
                print("❌ [ASR ERROR]:", data)
                continue

            if "result" in data:
                text = data["result"].get("text", "")
                if text:
                    print("📝 [ASR TEXT]:", text)
                    final_text = text

        return final_text

    async def close(self):
        if self.ws:
            print("🧹 [ASR] closing session")
            try:
                await self.ws.close()
            finally:
                self.ws = None
                self.connected = False
                print("🧹 [ASR] session closed")
