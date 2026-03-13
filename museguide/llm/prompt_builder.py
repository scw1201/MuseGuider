from __future__ import annotations

from typing import Any, Dict, List

from museguide.llm.prompts import SYSTEM_PROMPT_CORE


def build_domain_prior_prompt(domain_cfg: dict) -> str:
    lines = ["以下是当前系统中可识别的展区与展品（包含空间信息）："]

    for zone in domain_cfg.get("zones", []):
        location = zone.get("location", {})
        floor = location.get("floor", "")
        area = location.get("area", "")
        description = location.get("description", "")
        zone_line = f"- 展区：{zone['name']}（{zone['id']}）"
        loc_parts = [part for part in [floor, area, description] if part]
        if loc_parts:
            zone_line += "｜位置：" + " / ".join(loc_parts)
        lines.append(zone_line)

        intro = zone.get("intro")
        if intro:
            lines.append(f"  简介：{intro}")

        for exhibit in zone.get("exhibits", []):
            alias_str = "、".join(exhibit.get("aliases", []))
            lines.append(f"  - 展品：{exhibit['name']}（{exhibit['id']}），别名：{alias_str}")

    return "\n".join(lines)


def build_guide_state_prompt(guide_states: dict) -> str:
    lines = []
    lines.append("你只能从以下导览员【身体动作状态】中选择一个作为 guide_state：\n")

    for state_name, cfg in guide_states.items():
        desc = cfg.get("llm_desc", "")
        lines.append(f"- {state_name}")
        if desc:
            lines.append(f"  {desc}")

    lines.append("\nguide_state 只描述导览员当前的【身体行为意图】，不要考虑任何实现细节。")
    return "\n".join(lines)


def build_base_system_prompt(domain_cfg: dict, guide_states: dict) -> str:
    return "\n\n".join([
        SYSTEM_PROMPT_CORE.strip(),
        build_guide_state_prompt(guide_states),
        build_domain_prior_prompt(domain_cfg),
    ])


def build_system_prompt(
    *,
    persona: Dict[str, Any],
    persona_id: str,
    base_system_prompt: str,
    context_text: str = "",
    force_english: bool = False,
) -> str:
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

    if _persona_requires_english(persona_id, persona):
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

    parts = [prefix, context_text, base_system_prompt]
    return "\n\n".join([part for part in parts if part])


def build_tour_progress_context(
    *,
    state: Dict[str, Any],
    user_text: str,
    domain_cfg: Dict[str, Any],
    normalize_text,
    recent_dialogue: str = "",
) -> str:
    if not state:
        return ""

    current_zone = str(state.get("current_zone", "")).strip()
    current_exhibit = str(state.get("current_exhibit", "")).strip()
    current_focus_status = str(state.get("current_focus_status", "")).strip()
    guide_stage = str(state.get("guide_stage", "")).strip()
    zone_progress = dict(state.get("zone_progress", {}) or {})
    exhibit_progress = dict(state.get("exhibit_progress", {}) or {})
    visited_zones = set(state.get("visited_zones", []) or [])
    visited_exhibits = set(state.get("visited_exhibits", []) or [])

    if not any([current_zone, current_exhibit, guide_stage, zone_progress, exhibit_progress]):
        return ""

    lines: List[str] = ["导览进程记忆："]
    zone_summaries: List[str] = []
    unseen_zones: List[str] = []
    for zone in domain_cfg.get("zones", []):
        zone_name = str(zone.get("name", "")).strip()
        status = str(zone_progress.get(zone_name, "unseen")).strip()
        if status == "unseen":
            unseen_zones.append(zone_name)
            continue
        zone_summaries.append(f"{zone_name}（{_zone_status_label(status)}）")
    if zone_summaries:
        lines.append("已涉及展区：" + "；".join(zone_summaries))
    if unseen_zones:
        lines.append("尚未涉及展区：" + "、".join(unseen_zones[:6]))
    zone_detail_lines = _build_zone_progress_lines(
        domain_cfg=domain_cfg,
        zone_progress=zone_progress,
        exhibit_progress=exhibit_progress,
        visited_zones=visited_zones,
        visited_exhibits=visited_exhibits,
    )
    if zone_detail_lines:
        lines.append("全馆导览进程：")
        lines.extend(zone_detail_lines)
    if current_zone:
        lines.append(f"当前聚焦展区：{current_zone}")
    if guide_stage:
        lines.append(f"当前导览阶段：{guide_stage}")
    if current_exhibit:
        focus_label = _exhibit_status_label(
            current_focus_status or exhibit_progress.get(current_exhibit, "brief")
        )
        lines.append(f"当前聚焦展品：{current_exhibit}（{focus_label}）")

    current_zone_cfg = _zone_by_name(domain_cfg, current_zone)
    if current_zone_cfg:
        detailed: List[str] = []
        brief: List[str] = []
        unseen: List[str] = []
        for exhibit in current_zone_cfg.get("exhibits", []) or []:
            exhibit_name = str(exhibit.get("name", "")).strip()
            status = str(exhibit_progress.get(exhibit_name, "unseen")).strip()
            if status == "detailed":
                detailed.append(exhibit_name)
            elif status == "brief":
                brief.append(exhibit_name)
            else:
                unseen.append(exhibit_name)
        if detailed:
            lines.append("当前展区已深入展品：" + "、".join(detailed))
        if brief:
            lines.append("当前展区已简述展品：" + "、".join(brief))
        if unseen:
            lines.append("当前展区未讲展品：" + "、".join(unseen))
        else:
            lines.append("当前展区展品已全部讲完。")

    if _is_next_item_request(user_text, normalize_text):
        lines.append("若用户要求继续看下一件/下一个，请优先选择当前展区仍未讲解的展品，不要重复已经点亮或已讲过的展品。只有当前展区没有未讲展品时，必须明确说明这个展厅已经看完，并询问是否前往下一个展厅。")

    if recent_dialogue:
        lines.append(recent_dialogue)

    lines.append("请基于以上进程推进讲解：你的回复内容和下一步引导都必须服从当前导览进程。避免重复完整概览，优先补未讲内容或把简要介绍推进到深入讲解。")
    return "\n".join(lines)


def _zone_by_name(domain_cfg: Dict[str, Any], zone_name: str) -> Dict[str, Any]:
    name = str(zone_name or "").strip()
    if not name:
        return {}
    for zone in domain_cfg.get("zones", []):
        if name == str(zone.get("name", "")).strip():
            return zone
    return {}


def _persona_requires_english(persona_id: str, persona: Dict[str, Any]) -> bool:
    return persona.get("language") == "en" or persona_id.startswith("eu_")


def _is_next_item_request(user_text: str, normalize_text) -> bool:
    normalized = normalize_text(user_text)
    if not normalized:
        return False
    keywords = [
        "下一件",
        "下一個",
        "下一个",
        "下个",
        "下一個展品",
        "下一个展品",
        "继续看",
        "继续往下看",
        "继续下一件",
        "next exhibit",
        "next one",
        "what next",
    ]
    return any(keyword in normalized for keyword in keywords)


def _zone_status_label(status: str) -> str:
    return {
        "unseen": "未讲解",
        "entered": "已进入",
        "overview": "已概览",
        "detailed": "已深入",
    }.get(str(status or "").strip(), "未知")


def _exhibit_status_label(status: str) -> str:
    return {
        "unseen": "未讲解",
        "brief": "简要介绍",
        "detailed": "深入讲解",
    }.get(str(status or "").strip(), "未知")


def _build_zone_progress_lines(
    *,
    domain_cfg: Dict[str, Any],
    zone_progress: Dict[str, str],
    exhibit_progress: Dict[str, str],
    visited_zones: set[str],
    visited_exhibits: set[str],
) -> List[str]:
    lines: List[str] = []
    for zone in domain_cfg.get("zones", []):
        if zone.get("category") == "facility":
            continue
        zone_name = str(zone.get("name", "")).strip()
        if not zone_name:
            continue
        zone_status = str(zone_progress.get(zone_name, "unseen")).strip()
        seen_exhibits: List[str] = []
        unseen_exhibits: List[str] = []
        for exhibit in zone.get("exhibits", []) or []:
            exhibit_name = str(exhibit.get("name", "")).strip()
            if not exhibit_name:
                continue
            exhibit_status = str(exhibit_progress.get(exhibit_name, "unseen")).strip()
            if exhibit_name in visited_exhibits or exhibit_status in {"brief", "detailed"}:
                seen_exhibits.append(
                    f"{exhibit_name}（{_exhibit_status_label(exhibit_status or 'brief')}）"
                )
            else:
                unseen_exhibits.append(exhibit_name)
        zone_seen = zone_name in visited_zones or zone_status not in {"", "unseen"}
        line = f"- {zone_name}：{_zone_status_label(zone_status if zone_seen else 'unseen')}"
        line += "；已看展品：" + ("、".join(seen_exhibits) if seen_exhibits else "无")
        line += "；未看展品：" + (
            "、".join(unseen_exhibits) if unseen_exhibits else "无（本展厅已看完）"
        )
        lines.append(line)
    return lines
