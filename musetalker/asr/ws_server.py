# musetalker/asr/ws_server.py
import asyncio
import struct
import websockets
import json

from musetalker.asr.v3_bigmodel_client import BigModelASR


def pcm_energy(b: bytes) -> int:
    if len(b) < 2:
        return 0
    n = len(b) // 2
    ints = struct.unpack("<" + "h" * n, b[: n * 2])
    return max(abs(x) for x in ints) if n else 0


async def handler(ws):
    print("✅ browser connected")
    asr = BigModelASR()
    final_text = ""
    last_sent = ""

    try:
        async for msg in ws:
            if not isinstance(msg, bytes):
                print("⚠️ [WS] non-bytes msg ignored:", type(msg))
                continue

            # STOP
            if len(msg) <= 2:
                print("🛑 STOP (from browser)")

                # 🔥 最关键：用 is_last=True 让 BigModelASR 内部自己 drain 尾包
                last = await asr.send_audio(b"", is_last=True)
                if last:
                    final_text = last

                print("📤 [WS] send final text to UI:", final_text)
                await ws.send(
                    json.dumps({"type": "final", "text": final_text}, ensure_ascii=False)
                )
                break

            # 正常音频
            e = pcm_energy(msg)
            print(f"📦 [WS] audio len={len(msg)} energy={e}")

            text = await asr.send_audio(msg, is_last=False)
            if text:
                final_text = text
                if text != last_sent:
                    last_sent = text
                    await ws.send(
                        json.dumps({"type": "partial", "text": text}, ensure_ascii=False)
                    )

    except websockets.exceptions.ConnectionClosed as e:
        print("⚠️ [WS] browser connection closed:", e)

    finally:
        await asr.close()
        print("🧹 ASR session closed")


async def main():
    print("🚀 ASR WS server on :9001")
    async with websockets.serve(
        handler,
        "0.0.0.0",
        9001,
        max_size=50 * 1024 * 1024,
        ping_interval=20,
        ping_timeout=20,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
