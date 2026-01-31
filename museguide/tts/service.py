# museguide/tts/service.py
import json
import socket
import base64
from pathlib import Path
import yaml


def load_tts_config():
    cfg_path = Path(__file__).parents[1] / "configs" / "tts.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["tts"]


class TTSService:
    def __init__(self):
        self.cfg = load_tts_config()
        self.host = self.cfg.get("worker_host", "127.0.0.1")
        self.port = int(self.cfg.get("worker_port", 8765))
        self.timeout = float(self.cfg.get("timeout", 30.0))

    def synthesize_stream(self, text, on_meta=None, on_pcm=None):
        """
        流式 TTS：
        - on_meta(meta_dict)
        - on_pcm(pcm_bytes)
        """
        req = {"text": text}

        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
            f = sock.makefile("r", encoding="utf-8")

            while True:
                line = f.readline()
                if not line:
                    raise RuntimeError("TTS worker closed")

                msg = json.loads(line)
                t = msg.get("type")

                if t == "meta":
                    if on_meta:
                        on_meta(msg)

                elif t == "audio":
                    pcm = base64.b64decode(msg["data"])
                    if on_pcm:
                        on_pcm(pcm)

                elif t == "end":
                    return msg

                elif t == "error":
                    raise RuntimeError(msg.get("error"))