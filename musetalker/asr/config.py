import yaml
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SECRETS_PATH = BASE_DIR / "configs" / "secrets.yaml"

with open(SECRETS_PATH, "r", encoding="utf-8") as f:
    _secrets = yaml.safe_load(f)

ASR_APPID = _secrets["asr"].get("appid") or _secrets["asr"].get("app_id")
ASR_TOKEN = _secrets["asr"].get("token") or _secrets["asr"].get("access_token")
ASR_CLUSTER = _secrets["asr"].get("cluster", "")
