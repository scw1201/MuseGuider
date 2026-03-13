from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from museguide.llm.guide_stage import (
    STAGE_EXHIBIT_DETAIL,
    STAGE_EXHIBIT_FOCUS,
    STAGE_EXHIBIT_OVERVIEW,
    STAGE_ROUTE_GUIDANCE,
    STAGE_ZONE_OVERVIEW,
    is_detail_stage,
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def normalize_zone(domain_cfg: Dict[str, Any], raw_zone: str) -> Tuple[str, str]:
    value = str(raw_zone or "").strip()
    if not value:
        return "", ""
    for zone in domain_cfg.get("zones", []):
        if value == zone.get("name") or value == zone.get("id"):
            return str(zone.get("name", "")).strip(), str(zone.get("id", "")).strip()
    for zone in domain_cfg.get("zones", []):
        zone_name = str(zone.get("name", "")).strip()
        if value and value in zone_name:
            return zone_name, str(zone.get("id", "")).strip()
    return value, ""


def normalize_exhibit(domain_cfg: Dict[str, Any], raw_exhibit: str, zone_id: str = "") -> Tuple[str, str]:
    value = str(raw_exhibit or "").strip()
    if not value or value == "未确定":
        return "未确定", ""
    for exhibits in [iter_exhibits(domain_cfg, zone_id), iter_exhibits(domain_cfg)]:
        for exhibit in exhibits:
            if value == exhibit.get("name") or value == exhibit.get("id"):
                return str(exhibit.get("name", "")).strip(), str(exhibit.get("id", "")).strip()
            aliases = exhibit.get("aliases", []) or []
            if value in aliases:
                return str(exhibit.get("name", "")).strip(), str(exhibit.get("id", "")).strip()
        for exhibit in exhibits:
            exhibit_name = str(exhibit.get("name", "")).strip()
            if value and value in exhibit_name:
                return exhibit_name, str(exhibit.get("id", "")).strip()
    return value, ""


def iter_exhibits(domain_cfg: Dict[str, Any], zone_id: str = "") -> List[Dict[str, Any]]:
    exhibits: List[Dict[str, Any]] = []
    for zone in domain_cfg.get("zones", []):
        if zone_id and str(zone.get("id", "")).strip() != zone_id:
            continue
        exhibits.extend(zone.get("exhibits", []) or [])
        if zone_id:
            break
    return exhibits


def infer_tour_event(
    *,
    result: Dict[str, Any],
    prior_state: Dict[str, Any],
    zone_id: str,
    exhibit_id: str,
    domain_cfg: Dict[str, Any],
) -> str:
    user_intent = str(result.get("user_intent", "")).strip()
    guide_state = str(result.get("guide_state", "")).strip()
    prev_zone = zone_id_from_name(domain_cfg, prior_state.get("current_zone", ""))
    prev_exhibit = exhibit_id_from_name(domain_cfg, prior_state.get("current_exhibit", ""))
    if exhibit_id:
        if exhibit_id != prev_exhibit:
            return "focus_exhibit"
        return "explain_exhibit"
    if any(keyword in user_intent for keyword in ["路线", "前往", "带路", "怎么走", "在哪", "开始导览"]):
        if zone_id and zone_id != prev_zone:
            return "enter_zone"
        return "transition_zone"
    if zone_id and zone_id != prev_zone:
        return "enter_zone"
    if guide_state == "POINTING_DIRECTION":
        return "transition_zone"
    return "explain_zone"


def collect_user_interests(
    *,
    domain_cfg: Dict[str, Any],
    prior_state: Dict[str, Any],
    zone_name: str,
    exhibit_name: str,
    user_text: str,
) -> List[str]:
    interests = list(prior_state.get("user_interests", []))
    for value in [zone_name, exhibit_name]:
        item = str(value or "").strip()
        if item and item != "未确定":
            interests.append(item)
    raw = str(user_text or "").strip()
    if raw:
        for zone in domain_cfg.get("zones", []):
            zone_name_cfg = str(zone.get("name", "")).strip()
            if zone_name_cfg and zone_name_cfg in raw:
                interests.append(zone_name_cfg)
            for exhibit in zone.get("exhibits", []) or []:
                exhibit_name_cfg = str(exhibit.get("name", "")).strip()
                if exhibit_name_cfg and exhibit_name_cfg in raw:
                    interests.append(exhibit_name_cfg)
                for alias in exhibit.get("aliases", []) or []:
                    alias_value = str(alias).strip()
                    if alias_value and alias_value in raw:
                        interests.append(exhibit_name_cfg or alias_value)
    deduped: List[str] = []
    seen: set[str] = set()
    for item in interests:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped[-8:]


def infer_zone_progress_status(result: Dict[str, Any], tour_event: str, exhibit_name: str) -> str:
    guide_stage = str(result.get("guide_stage", "")).strip()
    if exhibit_name and exhibit_name != "未确定":
        if is_detail_stage(guide_stage):
            return "detailed"
        return "overview"
    if tour_event == "enter_zone":
        return "entered"
    if guide_stage == STAGE_ZONE_OVERVIEW:
        return "overview"
    if guide_stage == STAGE_ROUTE_GUIDANCE:
        return "entered"
    if is_detail_stage(guide_stage):
        return "detailed"
    if guide_stage or tour_event in {"explain_zone", "transition_zone"}:
        return "overview"
    return "entered"


def infer_exhibit_progress_status(result: Dict[str, Any], tour_event: str, exhibit_name: str) -> str:
    if not exhibit_name or exhibit_name == "未确定":
        return ""
    guide_stage = str(result.get("guide_stage", "")).strip()
    if guide_stage == STAGE_EXHIBIT_DETAIL or tour_event == "explain_exhibit":
        return "detailed"
    if guide_stage in {STAGE_EXHIBIT_OVERVIEW, STAGE_EXHIBIT_FOCUS}:
        return "brief"
    return "brief"


def advance_zone_status(previous: str, current: str) -> str:
    return _advance_status(previous, current, {"unseen": 0, "entered": 1, "overview": 2, "detailed": 3})


def advance_exhibit_status(previous: str, current: str) -> str:
    return _advance_status(previous, current, {"unseen": 0, "brief": 1, "detailed": 2})


def zone_id_from_name(domain_cfg: Dict[str, Any], zone_name: str) -> str:
    _, zone_id = normalize_zone(domain_cfg, str(zone_name or ""))
    return zone_id


def exhibit_id_from_name(domain_cfg: Dict[str, Any], exhibit_name: str) -> str:
    _, exhibit_id = normalize_exhibit(domain_cfg, str(exhibit_name or ""))
    return exhibit_id


def _advance_status(previous: str, current: str, order: Dict[str, int]) -> str:
    prev_value = str(previous or "").strip()
    current_value = str(current or "").strip()
    if not current_value:
        return prev_value
    if order.get(current_value, -1) >= order.get(prev_value, -1):
        return current_value
    return prev_value
