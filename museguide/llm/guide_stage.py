from __future__ import annotations

from typing import Dict


STAGE_ROUTE_GUIDANCE = "引路阶段"
STAGE_ZONE_OVERVIEW = "展厅介绍"
STAGE_EXHIBIT_OVERVIEW = "展品介绍"
STAGE_EXHIBIT_FOCUS = "展品聚焦"
STAGE_EXHIBIT_DETAIL = "深入讲解"

GUIDE_STAGE_ORDER = [
    STAGE_ROUTE_GUIDANCE,
    STAGE_ZONE_OVERVIEW,
    STAGE_EXHIBIT_OVERVIEW,
    STAGE_EXHIBIT_FOCUS,
    STAGE_EXHIBIT_DETAIL,
]

GUIDE_STAGE_LABELS: Dict[str, str] = {
    STAGE_ROUTE_GUIDANCE: "用于指路、到达展区前后的移动引导，只更新位置，不默认进入具体展品。",
    STAGE_ZONE_OVERVIEW: "用于介绍某个展厅整体主题、看点和代表内容，仍以展厅为中心。",
    STAGE_EXHIBIT_OVERVIEW: "用于开始介绍某件展品，但先给简要信息，不展开到细节层。",
    STAGE_EXHIBIT_FOCUS: "用于明确把观众注意力引到某件具体展品上，强调请看这里、看哪里。",
    STAGE_EXHIBIT_DETAIL: "用于围绕当前展品做细节、背景、工艺、故事等深入讲解。",
}


def normalize_guide_stage(stage: str, *, has_exhibit: bool = False, is_route: bool = False) -> str:
    value = str(stage or "").strip()
    if not value:
        if is_route:
            return STAGE_ROUTE_GUIDANCE
        if has_exhibit:
            return STAGE_EXHIBIT_OVERVIEW
        return STAGE_ZONE_OVERVIEW

    if value in GUIDE_STAGE_LABELS:
        return value
    if any(keyword in value for keyword in ["引路", "路线", "前往", "移动", "带路"]):
        return STAGE_ROUTE_GUIDANCE
    if any(keyword in value for keyword in ["概览", "展厅", "展区", "区域", "整体"]):
        return STAGE_ZONE_OVERVIEW if not has_exhibit else STAGE_EXHIBIT_OVERVIEW
    if any(keyword in value for keyword in ["聚焦", "请看", "焦点", "关注"]):
        return STAGE_EXHIBIT_FOCUS
    if any(keyword in value for keyword in ["深入", "细节", "补充", "背景", "详细"]):
        return STAGE_EXHIBIT_DETAIL if has_exhibit else STAGE_ZONE_OVERVIEW
    if any(keyword in value for keyword in ["展品", "文物", "作品", "器物"]):
        return STAGE_EXHIBIT_OVERVIEW if has_exhibit else STAGE_ZONE_OVERVIEW
    if is_route:
        return STAGE_ROUTE_GUIDANCE
    if has_exhibit:
        return STAGE_EXHIBIT_OVERVIEW
    return STAGE_ZONE_OVERVIEW


def is_zone_stage(stage: str) -> bool:
    return stage in {STAGE_ROUTE_GUIDANCE, STAGE_ZONE_OVERVIEW}


def is_exhibit_stage(stage: str) -> bool:
    return stage in {STAGE_EXHIBIT_OVERVIEW, STAGE_EXHIBIT_FOCUS, STAGE_EXHIBIT_DETAIL}


def is_detail_stage(stage: str) -> bool:
    return stage == STAGE_EXHIBIT_DETAIL
