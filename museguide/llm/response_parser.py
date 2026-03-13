from __future__ import annotations

import json
import re
from typing import Any, Dict

from museguide.llm.guide_stage import (
    STAGE_EXHIBIT_FOCUS,
    STAGE_ROUTE_GUIDANCE,
    normalize_guide_stage,
)


def parse_llm_json(text: str) -> Dict[str, Any]:
    if not text:
        raise RuntimeError("LLM returned empty text")

    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(text.lstrip())
    except json.JSONDecodeError as error:
        repaired = repair_truncated_json(text)
        if repaired and repaired != text:
            try:
                data, _ = decoder.raw_decode(repaired.lstrip())
            except json.JSONDecodeError:
                recovered = recover_llm_json_fields(text)
                if recovered is None:
                    raise RuntimeError(f"LLM output is not valid JSON:\n{text}") from error
                data = recovered
        else:
            recovered = recover_llm_json_fields(text)
            if recovered is None:
                raise RuntimeError(f"LLM output is not valid JSON:\n{text}") from error
            data = recovered

    data = fill_llm_json_defaults(data)
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


def fill_llm_json_defaults(data: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(data or {})
    merged["tts_text"] = str(merged.get("tts_text", "") or "").strip()
    merged["guide_zone"] = str(merged.get("guide_zone", "") or "").strip()
    merged["guide_venue"] = str(merged.get("guide_venue", "") or "").strip() or "中华世纪坛"
    merged["guide_floor"] = str(merged.get("guide_floor", "") or "").strip() or "未确定"
    merged["guide_area"] = str(merged.get("guide_area", "") or "").strip() or "未确定"
    merged["focus_exhibit"] = str(merged.get("focus_exhibit", "") or "").strip() or "未确定"
    merged["user_intent"] = str(merged.get("user_intent", "") or "").strip() or "了解信息"
    merged["guide_stage"] = normalize_guide_stage(
        merged.get("guide_stage", ""),
        has_exhibit=merged["focus_exhibit"] != "未确定",
        is_route=any(
            keyword in merged["user_intent"]
            for keyword in ["路线", "前往", "带路", "怎么走", "在哪", "开始导览"]
        ),
    )
    merged["guide_state"] = normalize_guide_state(
        merged.get("guide_state", ""),
        guide_stage=merged["guide_stage"],
        has_exhibit=merged["focus_exhibit"] != "未确定",
    )
    confidence = merged.get("confidence")
    if confidence in (None, ""):
        merged["confidence"] = 0.75
    return merged


def repair_truncated_json(text: str) -> str:
    repaired = (text or "").rstrip()
    if not repaired:
        return repaired
    if repaired.count('"') % 2 == 1:
        repaired += '"'
    open_braces = repaired.count("{")
    close_braces = repaired.count("}")
    if close_braces < open_braces:
        repaired += "}" * (open_braces - close_braces)
    return repaired


def recover_llm_json_fields(text: str) -> Dict[str, Any] | None:
    raw = str(text or "")
    if not raw.strip():
        return None

    def extract_string(key: str) -> str:
        pattern = rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"'
        match = re.search(pattern, raw, flags=re.S)
        if match:
            try:
                return json.loads(f'"{match.group(1)}"')
            except json.JSONDecodeError:
                return match.group(1)

        prefix_pattern = rf'"{re.escape(key)}"\s*:\s*"([^"\n\r}}]*)'
        prefix_match = re.search(prefix_pattern, raw, flags=re.S)
        if prefix_match:
            return prefix_match.group(1).strip()
        return ""

    def extract_number(key: str) -> float | None:
        pattern = rf'"{re.escape(key)}"\s*:\s*(-?\d+(?:\.\d+)?)'
        match = re.search(pattern, raw)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    guide_state = extract_string("guide_state")
    tts_text = extract_string("tts_text")
    confidence = extract_number("confidence")
    guide_zone = extract_string("guide_zone")
    guide_venue = extract_string("guide_venue")
    guide_floor = extract_string("guide_floor")
    guide_area = extract_string("guide_area")
    focus_exhibit = extract_string("focus_exhibit")
    guide_stage = extract_string("guide_stage")
    user_intent = extract_string("user_intent")

    if not user_intent and '"user_intent' in raw:
        user_intent = "了解信息"

    minimum_required = [guide_state, tts_text, guide_zone, guide_venue, guide_floor, guide_area]
    if not all(minimum_required) or confidence is None:
        return None

    return {
        "guide_state": normalize_guide_state(
            guide_state,
            guide_stage=normalize_guide_stage(
                guide_stage,
                has_exhibit=(focus_exhibit or "未确定") != "未确定",
                is_route=False,
            ),
            has_exhibit=(focus_exhibit or "未确定") != "未确定",
        ),
        "tts_text": tts_text,
        "confidence": confidence,
        "guide_zone": guide_zone,
        "guide_venue": guide_venue,
        "guide_floor": guide_floor,
        "guide_area": guide_area,
        "focus_exhibit": focus_exhibit or "未确定",
        "guide_stage": normalize_guide_stage(
            guide_stage,
            has_exhibit=(focus_exhibit or "未确定") != "未确定",
            is_route=False,
        ),
        "user_intent": user_intent or "了解信息",
    }


def normalize_guide_state(raw_state: str, *, guide_stage: str, has_exhibit: bool) -> str:
    value = str(raw_state or "").strip()
    if value in {"GREETING_SELF", "EXPLAIN_DETAILED", "POINTING_DIRECTION", "FOCUS_EXHIBIT"}:
        return value
    if guide_stage == STAGE_ROUTE_GUIDANCE:
        return "POINTING_DIRECTION"
    if guide_stage == STAGE_EXHIBIT_FOCUS:
        return "FOCUS_EXHIBIT"
    if has_exhibit:
        return "EXPLAIN_DETAILED"
    return "EXPLAIN_DETAILED"
