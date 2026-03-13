import json
import re
from pathlib import Path
from typing import Dict, Any

import yaml
from volcenginesdkarkruntime import Ark

from museguide.llm.initiative import build_initiative_plan, merge_follow_up_prompt
from museguide.llm.context_store import ContextStore
from museguide.llm.prompt_builder import (
    build_base_system_prompt,
    build_system_prompt,
    build_tour_progress_context,
)
from museguide.llm.response_parser import parse_llm_json
from museguide.llm.tour_state_manager import (
    advance_exhibit_status,
    advance_zone_status,
    collect_user_interests,
    infer_exhibit_progress_status,
    infer_tour_event,
    infer_zone_progress_status,
    normalize_exhibit,
    normalize_text,
    normalize_zone,
)
from museguide.llm.guide_stage import (
    STAGE_EXHIBIT_DETAIL,
    STAGE_EXHIBIT_FOCUS,
    STAGE_EXHIBIT_OVERVIEW,
    STAGE_ROUTE_GUIDANCE,
    STAGE_ZONE_OVERVIEW,
    is_exhibit_stage,
)


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
        self.base_system_prompt = build_base_system_prompt(self.domain_cfg, self.guide_states)

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
        session_key = session_id or ""
        prior_state = self.context_store.get_session_state(session_key, persona_id)
        effective_user_text = self._resolve_user_text(user_text, prior_state)
        if self._is_start_command(effective_user_text):
            result = self._build_start_response(persona_id)
            result = self._apply_tour_state(result, effective_user_text, persona_id, session_key, prior_state)
            result = self._apply_video_mapping(result, persona_id)
            result = self._apply_initiative_plan(result, persona_id)
            self._persist_recommendation_state(session_key, persona_id, result)
            return result
        if self._should_transition_out_of_completed_zone(effective_user_text, prior_state):
            result = self._build_completed_zone_transition_response(persona_id, prior_state)
            result = self._apply_tour_state(result, effective_user_text, persona_id, session_key, prior_state)
            result = self._apply_video_mapping(result, persona_id)
            self._persist_recommendation_state(session_key, persona_id, result)
            return result

        recent_dialogue = self.context_store.get_recent_dialogue(
            session_key,
            persona_id,
            max_turns=3,
        )
        progress_context = build_tour_progress_context(
            state=prior_state,
            user_text=effective_user_text,
            domain_cfg=self.domain_cfg,
            normalize_text=normalize_text,
            recent_dialogue=recent_dialogue,
        )
        system_prompt = self._build_system_prompt(persona_id, context_text=progress_context)
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
        raw_text = self._call_llm(effective_user_text, system_prompt)
        llm_data = parse_llm_json(raw_text)

        if self._persona_requires_english(persona_id) and self._contains_cjk(
            llm_data.get("tts_text", "")
        ):
            if self.llm_cfg.get("debug"):
                print("=== LANGUAGE RETRY ===")
                print("Chinese detected for EN persona, retrying with stricter prompt.")
                print("======================")
            strict_prompt = self._build_system_prompt(
                persona_id, context_text=progress_context, force_english=True
            )
            raw_text = self._call_llm(effective_user_text, strict_prompt)
            llm_data = parse_llm_json(raw_text)
            if self._contains_cjk(llm_data.get("tts_text", "")):
                if self.llm_cfg.get("debug"):
                    print("=== LANGUAGE FALLBACK ===")
                    print("Still non-English after retry, using fallback English prompt.")
                    print("=========================")
                llm_data["tts_text"] = (
                    "Hello, I am your museum guide. What would you like to explore today?"
                )

        result = self._translate_state_with_persona(llm_data, persona_id)
        result = self._apply_tour_state(result, effective_user_text, persona_id, session_key, prior_state)
        result = self._apply_video_mapping(result, persona_id)
        result = self._apply_initiative_plan(result, persona_id)
        self._persist_recommendation_state(session_key, persona_id, result)
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

    @staticmethod
    def _normalize_text(text: str) -> str:
        return normalize_text(text)

    def _is_start_command(self, user_text: str) -> bool:
        normalized = self._normalize_text(user_text)
        if not normalized:
            return False
        start_commands = {
            "开始导览",
            "开始讲解",
            "导览开始",
            "开始",
            "我们开始导览吧",
            "请启行导览",
            "start the tour",
            "start tour",
            "begin the tour",
        }
        return normalized in start_commands

    def _front_desk_zone(self) -> Dict[str, Any]:
        for zone in self.domain_cfg.get("zones", []):
            if zone.get("id") == "zone_front_desk":
                return zone
        return {}

    def _build_start_response(self, persona_id: str) -> Dict[str, Any]:
        front_desk = self._front_desk_zone()
        location = front_desk.get("location", {})
        llm_data = {
            "guide_state": "GREETING_SELF",
            "tts_text": self._build_start_tts(persona_id),
            "confidence": 0.98,
            "guide_zone": front_desk.get("name", "前台服务区"),
            "guide_venue": "中华世纪坛",
            "guide_floor": location.get("floor", "展馆一层"),
            "guide_area": location.get("area", "入口大厅"),
            "focus_exhibit": "未确定",
            "guide_stage": STAGE_ZONE_OVERVIEW,
            "user_intent": "开始导览",
        }
        return self._translate_state_with_persona(llm_data, persona_id)

    def _build_start_tts(self, persona_id: str) -> str:
        if self._persona_requires_english(persona_id):
            return (
                "Welcome. We have Chinese origins, calligraphy, world classics, "
                "and a children's discovery zone. Which would you like to explore first?"
            )

        if persona_id == "gu_man_demo":
            return (
                "诸位，馆中可观文明源流、书画雅韵、世界经典与童趣探索诸区。"
                "此刻想先往何处？"
            )

        if persona_id == "gu_woman_demo":
            return (
                "诸位，馆中备有文明源流、书画雅韵、世界经典与童趣探索诸区。"
                "诸位对哪一处更有兴味？"
            )

        if persona_id in {"boy_demo", "girl_demo"}:
            return (
                "我们可以先看文明起源、书画、世界文物，或者去互动体验区。"
                "你最想先看哪里？"
            )

        return (
            "欢迎来到中华世纪坛。这里有文明源流、书画文人、世界经典和互动体验等展区，"
            "您对哪一处更感兴趣？"
        )

    def _apply_initiative_plan(
        self, result: Dict[str, Any], persona_id: str
    ) -> Dict[str, Any]:
        plan = build_initiative_plan(result, persona_id, self.domain_cfg)
        merged = dict(result)
        merged["reply_text"] = str(merged.get("tts_text", "")).strip()
        merged["follow_up_text"] = plan.follow_up_prompt
        merged["tts_text"] = merge_follow_up_prompt(
            merged.get("tts_text", ""),
            plan.follow_up_prompt,
        )
        merged["suggested_actions"] = plan.suggested_actions
        merged["next_step_type"] = plan.next_step_type
        merged["next_step_target"] = plan.next_step_target
        merged["pending_action_type"] = plan.next_step_type
        merged["pending_action_target"] = plan.next_step_target
        pending_action = self._select_pending_action(
            suggested_actions=plan.suggested_actions,
            follow_up_text=plan.follow_up_prompt,
            next_step_type=plan.next_step_type,
            next_step_target=plan.next_step_target,
        )
        merged["pending_action_label"] = pending_action["label"]
        merged["pending_action_text"] = pending_action["text"]
        return merged

    def _apply_tour_state(
        self,
        result: Dict[str, Any],
        user_text: str,
        persona_id: str,
        session_id: str,
        prior_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = dict(result)
        zone_name, zone_id = normalize_zone(self.domain_cfg, merged.get("guide_zone", ""))
        exhibit_name, exhibit_id = normalize_exhibit(
            self.domain_cfg,
            merged.get("focus_exhibit", ""),
            zone_id=zone_id,
        )
        guide_stage = str(merged.get("guide_stage", "")).strip()
        if not is_exhibit_stage(guide_stage):
            exhibit_name = "未确定"
            exhibit_id = ""
        merged["guide_zone"] = zone_name
        merged["focus_exhibit"] = exhibit_name

        tour_event = infer_tour_event(
            result=merged,
            prior_state=prior_state,
            zone_id=zone_id,
            exhibit_id=exhibit_id,
            domain_cfg=self.domain_cfg,
        )
        zone_progress = dict(prior_state.get("zone_progress", {}))
        exhibit_progress = dict(prior_state.get("exhibit_progress", {}))
        zone_status = infer_zone_progress_status(merged, tour_event, exhibit_name)
        exhibit_status = infer_exhibit_progress_status(merged, tour_event, exhibit_name)
        if zone_name:
            zone_progress[zone_name] = advance_zone_status(
                zone_progress.get(zone_name, ""),
                zone_status,
            )
        if exhibit_name and exhibit_name != "未确定":
            exhibit_progress[exhibit_name] = advance_exhibit_status(
                exhibit_progress.get(exhibit_name, ""),
                exhibit_status,
            )
        user_interests = collect_user_interests(
            domain_cfg=self.domain_cfg,
            prior_state=prior_state,
            zone_name=zone_name,
            exhibit_name=exhibit_name,
            user_text=user_text,
        )
        session_state = self.context_store.update(
            session_id,
            persona_id,
            user_text=user_text,
            guide_text=merged.get("tts_text", ""),
            current_zone=zone_name,
            current_exhibit=exhibit_name if exhibit_name != "未确定" and is_exhibit_stage(guide_stage) else "",
            current_focus_status=exhibit_status if exhibit_name and exhibit_name != "未确定" else zone_progress.get(zone_name, ""),
            guide_stage=merged.get("guide_stage", ""),
            reply_text=merged.get("reply_text", ""),
            follow_up_text=merged.get("follow_up_text", ""),
            pending_action_label=merged.get("pending_action_label", ""),
            pending_action_text=merged.get("pending_action_text", ""),
            pending_action_type=merged.get("pending_action_type", ""),
            pending_action_target=merged.get("pending_action_target", ""),
            visited_zones=[zone_name] if zone_name else [],
            visited_exhibits=[exhibit_name] if exhibit_name and exhibit_name != "未确定" and is_exhibit_stage(guide_stage) else [],
            zone_progress=zone_progress,
            exhibit_progress=exhibit_progress,
            user_interests=user_interests,
            tour_event=tour_event,
        )
        merged["tour_event"] = session_state.get("tour_event", "")
        merged["current_zone"] = session_state.get("current_zone", "")
        merged["current_exhibit"] = session_state.get("current_exhibit", "")
        merged["current_focus_status"] = session_state.get("current_focus_status", "")
        merged["reply_text"] = session_state.get("reply_text", "")
        merged["follow_up_text"] = session_state.get("follow_up_text", "")
        merged["pending_action_label"] = session_state.get("pending_action_label", "")
        merged["pending_action_text"] = session_state.get("pending_action_text", "")
        merged["pending_action_type"] = session_state.get("pending_action_type", "")
        merged["pending_action_target"] = session_state.get("pending_action_target", "")
        merged["visited_zones"] = session_state.get("visited_zones", [])
        merged["visited_exhibits"] = session_state.get("visited_exhibits", [])
        merged["zone_progress"] = session_state.get("zone_progress", {})
        merged["exhibit_progress"] = session_state.get("exhibit_progress", {})
        merged["user_interests"] = session_state.get("user_interests", [])
        return merged

    def _apply_video_mapping(self, result: Dict[str, Any], persona_id: str) -> Dict[str, Any]:
        merged = dict(result)
        mapped_guide_state = self._mapped_guide_state(merged)
        translated = self._translate_state_with_persona(
            {
                "guide_state": mapped_guide_state,
                "guide_zone": merged.get("guide_zone", ""),
                "guide_venue": merged.get("guide_venue", ""),
                "guide_floor": merged.get("guide_floor", ""),
                "guide_area": merged.get("guide_area", ""),
                "focus_exhibit": merged.get("focus_exhibit", ""),
                "guide_stage": merged.get("guide_stage", ""),
                "user_intent": merged.get("user_intent", ""),
            },
            persona_id,
        )
        merged["guide_state"] = translated["guide_state"]
        merged["video_state"] = translated["video_state"]
        merged["video_dir"] = translated["video_dir"]
        merged["video_prefix"] = translated["video_prefix"]
        if "tts_voice_type" in translated:
            merged["tts_voice_type"] = translated["tts_voice_type"]
        merged["video_mapping_source"] = "deterministic"
        return merged

    def _mapped_guide_state(self, result: Dict[str, Any]) -> str:
        user_intent = str(result.get("user_intent", "") or "").strip()
        guide_stage = str(result.get("guide_stage", "") or "").strip()
        tour_event = str(result.get("tour_event", "") or "").strip()
        focus_exhibit = str(result.get("focus_exhibit", "") or "").strip()

        if user_intent == "开始导览":
            return "GREETING_SELF"
        if guide_stage == STAGE_ROUTE_GUIDANCE or tour_event in {"transition_zone", "enter_zone"}:
            return "POINTING_DIRECTION"
        if guide_stage == STAGE_EXHIBIT_FOCUS or tour_event == "focus_exhibit":
            return "FOCUS_EXHIBIT"
        if guide_stage in {STAGE_ZONE_OVERVIEW, STAGE_EXHIBIT_OVERVIEW, STAGE_EXHIBIT_DETAIL}:
            return "EXPLAIN_DETAILED"
        if focus_exhibit and focus_exhibit != "未确定":
            return "EXPLAIN_DETAILED"
        return "EXPLAIN_DETAILED"

    def _resolve_user_text(self, user_text: str, prior_state: Dict[str, Any]) -> str:
        raw = str(user_text or "").strip()
        if not raw:
            return raw
        normalized = self._normalize_affirmation_text(raw)
        if self._is_affirmation_reply(normalized):
            pending_action_text = str(prior_state.get("pending_action_text", "") or "").strip()
            pending_action_label = str(prior_state.get("pending_action_label", "") or "").strip()
            pending_action_type = str(prior_state.get("pending_action_type", "") or "").strip()
            pending_action_target = str(prior_state.get("pending_action_target", "") or "").strip()
            if pending_action_text:
                label = pending_action_label or "上一轮推荐"
                return (
                    f"用户确认执行上一轮推荐动作。"
                    f"动作类型：{pending_action_type or '未指定'}。"
                    f"{f'目标：{pending_action_target}。' if pending_action_target else ''}"
                    f"动作标签：{label}。"
                    f"请直接执行该动作并继续推进，不要停留在原话题。"
                    f"执行指令：{pending_action_text}"
                )
            current_zone = str(prior_state.get("current_zone", "") or "").strip()
            current_exhibit = str(prior_state.get("current_exhibit", "") or "").strip()
            current_stage = str(prior_state.get("guide_stage", "") or "").strip()
            return (
                "用户正在确认并要求继续推进当前导览，不是闲聊附和。"
                f"{f'当前展区：{current_zone}。' if current_zone else ''}"
                f"{f'当前展品：{current_exhibit}。' if current_exhibit else ''}"
                f"{f'当前导览阶段：{current_stage}。' if current_stage else ''}"
                "请直接往下推进：如果当前在讲展品，就继续深入或切到当前展区下一件未讲展品；"
                "如果当前在展厅介绍或引路，就把观众推进到下一步，不要重复上一句。"
            )
        return raw

    def _is_affirmation_reply(self, normalized: str) -> bool:
        value = str(normalized or "").strip()
        if not value:
            return False
        exact_matches = {
            "好", "好的", "好啊", "好呀", "好呢", "好哇", "可以", "可以啊", "可以的",
            "行", "行啊", "行的", "行吧", "嗯", "嗯嗯", "恩", "是", "是的", "对", "对的",
            "对啊", "没错", "没问题", "可以呀", "当然", "当然可以", "可以可以",
            "要", "要啊", "要的", "要呀", "要吧", "要要要", "想", "想的",
            "想看", "想听", "想去", "想啊", "好的呀", "好的呢",
            "就这个", "就这样", "就按这个", "那就这样", "那就这么办",
            "ok", "okay", "sure", "yes", "yep", "right",
        }
        if value in exact_matches:
            return True
        prefix_matches = (
            "那就", "就要", "就看", "就听", "就去", "那就去", "那就看", "那就听",
            "那先", "先看", "先听", "先去", "带我去", "那带我去", "麻烦带我去",
            "请带我去", "来吧", "走吧", "可以就", "那可以", "可以先", "要不就",
            "yes ", "ok ", "okay ", "sure ",
        )
        if any(value.startswith(prefix) for prefix in prefix_matches):
            return True
        suffix_matches = ("吧", "呀", "啊", "呢")
        short_stems = {"好", "行", "对", "要", "想", "嗯", "是"}
        for suffix in suffix_matches:
            if value.endswith(suffix):
                stem = value[: -len(suffix)].strip()
                if stem in short_stems:
                    return True
        return False

    def _normalize_affirmation_text(self, raw: str) -> str:
        value = normalize_text(raw)
        value = re.sub(r"[，。！？、,.!?~～…；;:\"'（）()【】\[\]]+", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        fillers = ("吧", "呀", "啊", "呢", "啦", "嘛", "呗", "诶", "欸")
        changed = True
        while changed and value:
            changed = False
            for filler in fillers:
                if value.endswith(filler):
                    value = value[: -len(filler)].strip()
                    changed = True
        return value

    def _select_pending_action(
        self,
        *,
        suggested_actions: list[Dict[str, str]],
        follow_up_text: str,
        next_step_type: str,
        next_step_target: str,
    ) -> Dict[str, str]:
        actions = list(suggested_actions or [])
        if not actions:
            return {"label": "", "text": ""}

        follow_up = str(follow_up_text or "").strip()
        action_type = str(next_step_type or "").strip()
        target = str(next_step_target or "").strip()

        keyword_groups = []
        if any(token in follow_up for token in ["先讲", "重点展品", "代表展品", "到了"]):
            keyword_groups.append(("先讲", "重点", "代表", "展品"))
        if any(token in follow_up for token in ["细节", "精妙", "继续深挖", "深入"]):
            keyword_groups.append(("细节", "深挖", "背景", "故事"))
        if any(token in follow_up for token in ["下一个展厅", "下一展厅", "下一站", "移步"]):
            keyword_groups.append(("下一站", "下一厅", "移步", "前往", "带我去"))
        if action_type in {"recommend_exhibit", "deepen_exhibit"} and target:
            keyword_groups.append((target,))
        if action_type in {"transition_zone", "offer_route"} and target:
            keyword_groups.append((target, "前往", "带我去", "下一站"))

        for keywords in keyword_groups:
            for action in actions:
                label = str(action.get("label", "")).strip()
                text = str(action.get("text", "")).strip()
                haystack = f"{label} {text}"
                if all(keyword in haystack for keyword in keywords if keyword):
                    return {"label": label, "text": text}
            for action in actions:
                label = str(action.get("label", "")).strip()
                text = str(action.get("text", "")).strip()
                haystack = f"{label} {text}"
                if any(keyword in haystack for keyword in keywords if keyword):
                    return {"label": label, "text": text}

        first = actions[0]
        return {
            "label": str(first.get("label", "")).strip(),
            "text": str(first.get("text", "")).strip(),
        }

    def _should_transition_out_of_completed_zone(
        self,
        user_text: str,
        prior_state: Dict[str, Any],
    ) -> bool:
        current_zone = str(prior_state.get("current_zone", "")).strip()
        if not current_zone:
            return False
        if not self._is_next_item_request(user_text):
            return False
        zone = self._zone_by_name(current_zone)
        exhibits = list(zone.get("exhibits", []) or [])
        if not exhibits:
            return False
        visited_exhibits = {
            str(name or "").strip()
            for name in (prior_state.get("visited_exhibits", []) or [])
            if str(name or "").strip()
        }
        exhibit_progress = dict(prior_state.get("exhibit_progress", {}) or {})
        for exhibit in exhibits:
            exhibit_name = str(exhibit.get("name", "")).strip()
            if exhibit_name in visited_exhibits:
                continue
            status = str(exhibit_progress.get(exhibit_name, "unseen")).strip()
            if status not in {"brief", "detailed"}:
                return False
        return True

    def _build_completed_zone_transition_response(
        self,
        persona_id: str,
        prior_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_zone = str(prior_state.get("current_zone", "")).strip() or "当前展厅"
        current_zone_cfg = self._zone_by_name(current_zone)
        location = current_zone_cfg.get("location", {}) if current_zone_cfg else {}
        next_zones = self._next_unseen_zones(prior_state, current_zone)
        next_zone_name = next_zones[0] if next_zones else ""

        if self._persona_requires_english(persona_id):
            reply_text = (
                f"We have finished all exhibits in the {current_zone}."
                if current_zone else
                "We have finished this gallery."
            )
            follow_up_text = (
                f"Would you like to continue to the {next_zone_name}?"
                if next_zone_name else
                "Would you like to continue to the next gallery?"
            )
        elif persona_id in {"boy_demo", "girl_demo"}:
            reply_text = f"{current_zone}已经全部看完啦。"
            follow_up_text = (
                f"要不要我带你去下一个展厅{next_zone_name}？"
                if next_zone_name else
                "要不要我带你去下一个展厅？"
            )
        elif persona_id in {"gu_man_demo", "gu_woman_demo"}:
            reply_text = f"{current_zone}诸件展品已尽览。"
            follow_up_text = (
                f"可要移步前往下一展厅{next_zone_name}？"
                if next_zone_name else
                "可要移步下一展厅？"
            )
        else:
            reply_text = f"{current_zone}已经全部看完了。"
            follow_up_text = (
                f"您要不要继续去下一个展厅{next_zone_name}？"
                if next_zone_name else
                "您要不要继续去下一个展厅？"
            )

        suggested_actions = []
        for zone_name in next_zones[:2]:
            suggested_actions.append({
                "label": zone_name.replace("展区", "").replace("体验区", "体验"),
                "text": f"带我去{zone_name}。",
            })
        suggested_actions.append({
            "label": "你来推荐" if persona_id not in {"gu_man_demo", "gu_woman_demo"} else "烦请推荐",
            "text": "请推荐我接下来去哪个展厅。",
        })

        response = self._translate_state_with_persona({
            "guide_state": "EXPLAIN_DETAILED",
            "tts_text": merge_follow_up_prompt(reply_text, follow_up_text),
            "confidence": 0.98,
            "guide_zone": current_zone,
            "guide_venue": "中华世纪坛",
            "guide_floor": location.get("floor", prior_state.get("guide_floor", "未确定")),
            "guide_area": location.get("area", prior_state.get("guide_area", "未确定")),
            "focus_exhibit": "未确定",
            "guide_stage": STAGE_ROUTE_GUIDANCE,
            "user_intent": "请求下一展厅",
        }, persona_id)
        response["reply_text"] = reply_text
        response["follow_up_text"] = follow_up_text
        response["suggested_actions"] = suggested_actions
        response["next_step_type"] = "transition_zone"
        response["next_step_target"] = next_zone_name or "下一展厅"
        response["pending_action_type"] = "transition_zone"
        response["pending_action_target"] = next_zone_name or "下一展厅"
        if suggested_actions:
            response["pending_action_label"] = suggested_actions[0]["label"]
            response["pending_action_text"] = suggested_actions[0]["text"]
        else:
            response["pending_action_label"] = ""
            response["pending_action_text"] = ""
        return response

    def _is_next_item_request(self, user_text: str) -> bool:
        normalized = normalize_text(user_text)
        if not normalized:
            return False
        keywords = [
            "下一件", "下一个", "下个", "下一個", "继续看", "继续往下看", "继续下一件",
            "next exhibit", "next one", "what next",
        ]
        return any(keyword in normalized for keyword in keywords)

    def _zone_by_name(self, zone_name: str) -> Dict[str, Any]:
        name = str(zone_name or "").strip()
        if not name:
            return {}
        for zone in self.domain_cfg.get("zones", []):
            if name == str(zone.get("name", "")).strip():
                return zone
        return {}

    def _next_unseen_zones(self, prior_state: Dict[str, Any], current_zone: str) -> list[str]:
        zone_progress = dict(prior_state.get("zone_progress", {}) or {})
        visited_zones = set(prior_state.get("visited_zones", []) or [])
        result: list[str] = []
        for zone in self.domain_cfg.get("zones", []):
            zone_name = str(zone.get("name", "")).strip()
            if not zone_name or zone_name == current_zone or zone.get("category") == "facility":
                continue
            status = str(zone_progress.get(zone_name, "unseen")).strip()
            if zone_name not in visited_zones and status in {"", "unseen"}:
                result.append(zone_name)
        if result:
            return result
        for zone in self.domain_cfg.get("zones", []):
            zone_name = str(zone.get("name", "")).strip()
            if not zone_name or zone_name == current_zone or zone.get("category") == "facility":
                continue
            result.append(zone_name)
        return result

    def _persist_recommendation_state(
        self,
        session_id: str,
        persona_id: str,
        result: Dict[str, Any],
    ) -> None:
        if not session_id:
            return
        persisted = self.context_store.set_pending_recommendation(
            session_id,
            persona_id,
            reply_text=str(result.get("reply_text", "")).strip(),
            follow_up_text=str(result.get("follow_up_text", "")).strip(),
            pending_action_label=str(result.get("pending_action_label", "")).strip(),
            pending_action_text=str(result.get("pending_action_text", "")).strip(),
            pending_action_type=str(result.get("pending_action_type", "")).strip(),
            pending_action_target=str(result.get("pending_action_target", "")).strip(),
        )
        result["reply_text"] = persisted.get("reply_text", "")
        result["follow_up_text"] = persisted.get("follow_up_text", "")
        result["pending_action_label"] = persisted.get("pending_action_label", "")
        result["pending_action_text"] = persisted.get("pending_action_text", "")
        result["pending_action_type"] = persisted.get("pending_action_type", "")
        result["pending_action_target"] = persisted.get("pending_action_target", "")

    def _build_system_prompt(
        self,
        persona_id: str,
        context_text: str = "",
        force_english: bool = False,
    ) -> str:
        persona = self._get_persona(persona_id)
        return build_system_prompt(
            persona=persona,
            persona_id=persona_id,
            base_system_prompt=self.base_system_prompt,
            context_text=context_text,
            force_english=force_english,
        )

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
