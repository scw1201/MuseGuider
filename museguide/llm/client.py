from volcenginesdkarkruntime import Ark
from pathlib import Path
import yaml

class LLMClient:
    def __init__(self, model: str, timeout: int = 10):
        self.model = model
        secrets_path = Path(__file__).parents[1] / "configs" / "secrets.yaml"
        with open(secrets_path, "r", encoding="utf-8") as f:
            secrets = yaml.safe_load(f) or {}
        api_key = secrets.get("doubao", {}).get("api_key", "")
        self.client = Ark(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=api_key,
            timeout=timeout
        )

    def chat(self, system_prompt: str, user_text: str):
        return self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            max_output_tokens=200,
            temperature=0.2,
        )
