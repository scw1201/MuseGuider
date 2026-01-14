import json
from pathlib import Path
from typing import Dict, Any

import yaml
from volcenginesdkarkruntime import Ark

from musetalker.llm.prompts import SYSTEM_PROMPT_CORE
from musetalker.llm.context_store import ContextStore


# =============================
# Config loaders
# =============================

def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_secrets() -> dict:
    return load_yaml(Path(__file__).parents[1] / "configs" / "secrets.yaml")


def load_llm_config() -> dict:
    return load_yaml(Path(__file__).parents[1] / "configs" / "llm.yaml")["llm"]


def load_domain_prior() -> dict:
    path = Path(__file__).parents[1] / "configs" / "domain_prior.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_guide_states() -> dict:
    return load_yaml(Path(__file__).parents[1] / "configs" / "guide_states.yaml")

def load_personas() -> dict:
    data = load_yaml(Path(__file__).parents[1] / "configs" / "personas.yaml")
    return data.get("personas", {})


# =============================
# Prompt builders
# =============================

def build_domain_prior_prompt(domain_cfg: dict) -> str:
    lines = ["以下是当前系统中可识别的展区与展品（包含空间信息）："]

    for z in domain_cfg.get("zones", []):
        loc = z.get("location", {})
        floor = loc.get("floor", "")
        area = loc.get("area", "")
        desc = loc.get("description", "")
        zone_line = f"- 展区：{z['name']}（{z['id']}）"
        loc_parts = [p for p in [floor, area, desc] if p]
        if loc_parts:
            zone_line += "｜位置：" + " / ".join(loc_parts)
        lines.append(zone_line)

        intro = z.get("intro")
        if intro:
            lines.append(f"  简介：{intro}")

        for e in z.get("exhibits", []):
            alias_str = "、".join(e.get("aliases", []))
            lines.append(f"  - 展品：{e['name']}（{e['id']}），别名：{alias_str}")

    return "\n".join(lines)


def build_guide_state_prompt(guide_states: dict) -> str:
    lines = []
    lines.append("你只能从以下导览员【身体动作状态】中选择一个作为 guide_state：\n")

    for k, v in guide_states.items():
        desc = v.get("llm_desc", "")
        lines.append(f"- {k}")
        if desc:
            lines.append(f"  {desc}")

    lines.append("\nguide_state 只描述导览员当前的【身体行为意图】，不要考虑任何实现细节。")
    return "\n".join(lines)


# =============================
# Orchestrator
# =============================

class LLMOrchestrator:
    """
    user_text
        → LLM（guide_state + tts）
        → 翻译为前端 / 视频可用的结构
    """

    def __init__(self):
        # configs
        self.llm_cfg = load_llm_config()
        self.domain_cfg = load_domain_prior()
        self.guide_states = load_guide_states()
        self.secrets = load_secrets()
        self.personas = load_personas()
        self.default_persona_id = "woman_demo"
        self.context_store = ContextStore()

        # LLM client
        self.client = Ark(
            base_url=self.llm_cfg["base_url"],
            api_key=self.secrets["doubao"]["api_key"],
            timeout=self.llm_cfg.get("timeout", 10),
        )

        # ===== system prompt（一次性构建）=====
        self.base_system_prompt = "\n\n".join([
            SYSTEM_PROMPT_CORE.strip(),
            build_guide_state_prompt(self.guide_states),
            build_domain_prior_prompt(self.domain_cfg),
        ])

        if self.llm_cfg.get("debug"):
            print("=== SYSTEM PROMPT ===")
            print(self.base_system_prompt)
            print("=" * 60)

    # -------------------------
    # Public API
    # -------------------------

    def run(
        self,
        user_text: str,
        persona_id: str = "woman_demo",
        session_id: str | None = None,
    ) -> Dict[str, Any]:
        context_text = self.context_store.get(session_id or "", persona_id)
        system_prompt = self._build_system_prompt(persona_id, context_text=context_text)
        if self.llm_cfg.get("debug"):
            persona = self._get_persona(persona_id)
            print("=== PERSONA USED ===")
            print({
                "persona_id": persona_id,
                "display_name": persona.get("display_name"),
            })
            print("====================")
            print("=== SYSTEM PROMPT (HEAD) ===")
            print(system_prompt[:800])
            print("=== SYSTEM PROMPT (TAIL) ===")
            print(system_prompt[-800:])
            print("============================")
        raw_text = self._call_llm(user_text, system_prompt)
        llm_data = self._parse_llm_json(raw_text)

        if self._persona_requires_english(persona_id) and self._contains_cjk(
            llm_data.get("tts_text", "")
        ):
            if self.llm_cfg.get("debug"):
                print("=== LANGUAGE RETRY ===")
                print("Chinese detected for EN persona, retrying with stricter prompt.")
                print("======================")
            strict_prompt = self._build_system_prompt(
                persona_id, context_text=context_text, force_english=True
            )
            raw_text = self._call_llm(user_text, strict_prompt)
            llm_data = self._parse_llm_json(raw_text)
            if self._contains_cjk(llm_data.get("tts_text", "")):
                if self.llm_cfg.get("debug"):
                    print("=== LANGUAGE FALLBACK ===")
                    print("Still non-English after retry, using fallback English prompt.")
                    print("=========================")
                llm_data["tts_text"] = (
                    "Hello, I am your museum guide. What would you like to explore today?"
                )

        result = self._translate_state_with_persona(llm_data, persona_id)
        location_text = " / ".join([
            p for p in [
                result.get("guide_venue", ""),
                result.get("guide_floor", ""),
                result.get("guide_area", ""),
                result.get("guide_zone", ""),
            ]
            if p
        ])
        self.context_store.set(
            session_id or "",
            persona_id,
            user_text,
            result.get("tts_text", ""),
            location_text,
        )
        return result

    # -------------------------
    # Internal
    # -------------------------

    def _call_llm(self, user_text: str, system_prompt: str) -> str:
        resp = self.client.responses.create(
            model=self.llm_cfg["model"],
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            thinking={"type": "disabled"},
            max_output_tokens=self.llm_cfg.get("max_output_tokens", 300),
            temperature=self.llm_cfg.get("temperature", 0.2),
        )

        # ===== 强制日志（你现在阶段必须留）=====
        print("=== ARK RAW RESPONSE ===")
        print(resp)
        print("========================")

        text = self._extract_text(resp)

        print("=== EXTRACTED TEXT ===")
        print(repr(text))
        print("======================")

        return text

    def _get_persona(self, persona_id: str) -> Dict[str, Any]:
        if not self.personas:
            return {}
        if persona_id in self.personas:
            return self.personas[persona_id]
        if self.default_persona_id in self.personas:
            return self.personas[self.default_persona_id]
        return next(iter(self.personas.values()))

    def _build_system_prompt(
        self,
        persona_id: str,
        context_text: str = "",
        force_english: bool = False,
    ) -> str:
        persona = self._get_persona(persona_id)
        prefix = (persona.get("prompt_prefix") or "").strip()
        self_ref = (persona.get("self_ref") or "").strip()
        user_address = (persona.get("user_address") or "").strip()
        if self_ref or user_address:
            prefix = "\n".join(filter(None, [
                prefix,
                "称呼与自称约束：",
                f"- 自称：{self_ref}" if self_ref else "",
                f"- 称呼用户：{user_address}" if user_address else "",
                "在 tts_text 中优先使用以上自称与称呼。",
            ]))
        if self._persona_requires_english(persona_id):
            prefix = "\n".join(filter(None, [
                prefix,
                "Language constraint: output JSON with tts_text in English only. Do not use Chinese.",
            ]))
            english_example = (
                '{\n'
                '  "guide_state": "GREETING_SELF",\n'
                '  "tts_text": "Hello, I am your museum guide. What would you like to explore today?",\n'
                '  "confidence": 0.9\n'
                '}'
            )
            prefix = "\n\n".join(filter(None, [
                prefix,
                "English example (follow this language):\n" + english_example,
            ]))
            if force_english:
                prefix = "\n".join(filter(None, [
                    prefix,
                    "Hard requirement: If any non-English appears in tts_text, the output is invalid.",
                ]))
        parts = [prefix, context_text, self.base_system_prompt]
        return "\n\n".join([p for p in parts if p])

    def _persona_requires_english(self, persona_id: str) -> bool:
        persona = self._get_persona(persona_id)
        return persona.get("language") == "en" or persona_id.startswith("eu_")

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in text)

    @staticmethod
    def _extract_text(resp) -> str:
        for item in resp.output:
            if item.type == "message":
                for c in item.content:
                    if c.type == "output_text":
                        return c.text.strip()
        return ""

    @staticmethod
    def _parse_llm_json(text: str) -> Dict[str, Any]:
        if not text:
            raise RuntimeError("LLM returned empty text")

        try:
            decoder = json.JSONDecoder()
            # Allow extra text after the JSON by parsing the first object.
            data, _ = decoder.raw_decode(text.lstrip())
        except json.JSONDecodeError as e:
            raise RuntimeError(f"LLM output is not valid JSON:\n{text}") from e

        required = {
            "guide_state",
            "tts_text",
            "confidence",
            "guide_zone",
            "guide_venue",
            "guide_floor",
            "guide_area",
            "focus_exhibit",
            "guide_stage",
            "user_intent",
        }
        missing = required - data.keys()
        if missing:
            raise RuntimeError(f"LLM JSON missing fields {missing}:\n{data}")

        return data

    def _translate_state(self, data: Dict[str, Any]) -> Dict[str, Any]:
        guide_state = data["guide_state"]

        if guide_state not in self.guide_states:
            raise RuntimeError(f"Unknown guide_state: {guide_state}")

        cfg = self.guide_states[guide_state]

        return {
            "guide_state": guide_state,
            "video_state": cfg["video_state"],
            "tts_text": data["tts_text"] if cfg.get("allow_tts", True) else "",
            "confidence": data["confidence"],
        }

    def _translate_state_with_persona(
        self, data: Dict[str, Any], persona_id: str
    ) -> Dict[str, Any]:
        result = self._translate_state(data)
        result.update({
            "guide_zone": data.get("guide_zone", ""),
            "guide_venue": data.get("guide_venue", ""),
            "guide_floor": data.get("guide_floor", ""),
            "guide_area": data.get("guide_area", ""),
            "focus_exhibit": data.get("focus_exhibit", ""),
            "guide_stage": data.get("guide_stage", ""),
            "user_intent": data.get("user_intent", ""),
        })
        persona = self._get_persona(persona_id)
        if persona:
            result["tts_voice_type"] = persona.get("tts_voice_type")
        return result
