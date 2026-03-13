from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from museguide.llm.guide_stage import (
    STAGE_EXHIBIT_DETAIL,
    STAGE_EXHIBIT_FOCUS,
    STAGE_EXHIBIT_OVERVIEW,
    STAGE_ROUTE_GUIDANCE,
    STAGE_ZONE_OVERVIEW,
)

@dataclass(frozen=True)
class InitiativePlan:
    next_step_type: str
    next_step_target: str
    follow_up_prompt: str
    suggested_actions: List[Dict[str, str]]


def build_initiative_plan(
    result: Dict[str, Any],
    persona_id: str,
    domain_cfg: Dict[str, Any],
) -> InitiativePlan:
    if _persona_requires_english(persona_id):
        return _build_english_plan(result, domain_cfg)
    return _build_chinese_plan(result, persona_id, domain_cfg)


def merge_follow_up_prompt(tts_text: str, follow_up_prompt: str) -> str:
    text = str(tts_text or "").strip()
    prompt = str(follow_up_prompt or "").strip()
    if not text or not prompt:
        return text
    if _has_question(text) or prompt in text:
        return text
    sep = " " if _is_english_text(text) else ""
    return f"{text}{sep}{prompt}".strip()


def dedupe_actions(actions: List[Dict[str, str]], limit: int = 3) -> List[Dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: List[Dict[str, str]] = []
    for action in actions:
        label = str(action.get("label", "")).strip()
        text = str(action.get("text", "")).strip()
        if not label or not text:
            continue
        key = (label, text)
        if key in seen:
            continue
        seen.add(key)
        result.append({"label": label, "text": text})
        if len(result) >= limit:
            break
    return result


def _build_english_plan(result: Dict[str, Any], domain_cfg: Dict[str, Any]) -> InitiativePlan:
    zone_name = _field(result, "guide_zone")
    exhibit_name = _field(result, "focus_exhibit")
    guide_stage = _field(result, "guide_stage")
    user_intent = _field(result, "user_intent")

    if user_intent == "开始导览" or guide_stage == STAGE_ZONE_OVERVIEW:
        return InitiativePlan(
            next_step_type="ask_zone",
            next_step_target="major_zones",
            follow_up_prompt="Which area would you like to start with?",
            suggested_actions=_opening_actions_en(domain_cfg),
        )

    if guide_stage == STAGE_ROUTE_GUIDANCE or any(keyword in user_intent for keyword in ["路线", "前往", "带路", "移动"]):
        zone = _get_zone_by_name(domain_cfg, zone_name) if zone_name else {}
        exhibits = zone.get("exhibits", [])
        return InitiativePlan(
            next_step_type="recommend_exhibit" if exhibits else "offer_route",
            next_step_target=zone_name or "next_stop",
            follow_up_prompt=(
                "After we arrive, would you like me to introduce the key exhibit there?"
                if exhibits else
                "Would you like me to guide you there now?"
            ),
            suggested_actions=_route_actions_en(zone_name, exhibits),
        )

    if exhibit_name and exhibit_name != "未确定" and guide_stage in {
        STAGE_EXHIBIT_OVERVIEW,
        STAGE_EXHIBIT_FOCUS,
        STAGE_EXHIBIT_DETAIL,
    }:
        return InitiativePlan(
            next_step_type="deepen_exhibit" if guide_stage in {STAGE_EXHIBIT_OVERVIEW, STAGE_EXHIBIT_FOCUS} else "recommend_exhibit",
            next_step_target=exhibit_name,
            follow_up_prompt=(
                "Would you like me to focus on one detail, explain the background, or move to the next exhibit?"
                if guide_stage in {STAGE_EXHIBIT_OVERVIEW, STAGE_EXHIBIT_FOCUS}
                else "Would you like one more detail, or should we move to the next unseen exhibit?"
            ),
            suggested_actions=dedupe_actions([
                _action("Explain details", f"Tell me more details about {exhibit_name}."),
                _action("Background story", f"What is the historical background of {exhibit_name}?"),
                _action("Next recommendation", "Recommend the next exhibit I should see."),
            ]),
        )

    if zone_name and zone_name not in {"前台服务区", "卫生间"}:
        zone = _get_zone_by_name(domain_cfg, zone_name)
        exhibits = zone.get("exhibits", [])
        actions = [
            _action("Zone highlight", f"What is the highlight of the {zone_name}?"),
            _action("Go deeper", f"Take me deeper into the {zone_name}."),
        ]
        next_target = zone_name
        next_type = "recommend_exhibit"
        if exhibits:
            actions.append(
                _action(
                    "Representative exhibit",
                    f"Recommend a representative exhibit in the {zone_name}.",
                )
            )
        else:
            next_type = "transition_zone"
            actions.append(_action("Next stop", "Recommend the next place I should visit."))
        return InitiativePlan(
            next_step_type=next_type,
            next_step_target=next_target,
            follow_up_prompt="Would you like to stay here or move to the next highlight?",
            suggested_actions=dedupe_actions(actions),
        )

    return InitiativePlan(
        next_step_type="ask_zone",
        next_step_target="major_zones",
        follow_up_prompt="Would you like a starting point or a short route?",
        suggested_actions=dedupe_actions([
            _action("Start with a classic", "Recommend a classic exhibit to begin with."),
            _action("Family-friendly", "Which area is best for a relaxed visit?"),
            _action("Route suggestion", "Plan a simple route for me."),
        ]),
    )


def _build_chinese_plan(
    result: Dict[str, Any],
    persona_id: str,
    domain_cfg: Dict[str, Any],
) -> InitiativePlan:
    zone_name = _field(result, "guide_zone")
    exhibit_name = _field(result, "focus_exhibit")
    guide_stage = _field(result, "guide_stage")
    user_intent = _field(result, "user_intent")
    is_child = persona_id in {"boy_demo", "girl_demo"}
    is_classic = persona_id in {"gu_man_demo", "gu_woman_demo"}
    next_unseen_exhibit = _next_unseen_exhibit(result, domain_cfg, zone_name, exhibit_name)
    next_unseen_zone = _next_unseen_zone(result, domain_cfg, zone_name)

    if user_intent == "开始导览" or guide_stage == STAGE_ZONE_OVERVIEW:
        return InitiativePlan(
            next_step_type="ask_zone",
            next_step_target="主要展区",
            follow_up_prompt=_cn_prompt(
                is_child,
                is_classic,
                regular="您想先听我带您看哪个展区？",
                child="你想先去哪个展区？",
                classic="诸位想先往哪一处？",
            ),
            suggested_actions=_opening_actions(result, domain_cfg, is_child, is_classic),
        )

    if guide_stage == STAGE_ROUTE_GUIDANCE or any(keyword in user_intent for keyword in ["路线", "前往", "带路", "怎么走", "在哪"]):
        zone = _get_zone_by_name(domain_cfg, zone_name) if zone_name else {}
        exhibits = zone.get("exhibits", [])
        return InitiativePlan(
            next_step_type="recommend_exhibit" if exhibits else "offer_route",
            next_step_target=zone_name or "下一站",
            follow_up_prompt=_cn_prompt(
                is_child,
                is_classic,
                regular=(
                    "到那里后，您要不要我先讲这个展厅最值得先看的展品？"
                    if exhibits else
                    "要不要我直接接着带您过去？"
                ),
                child=(
                    "到了那里以后，要不要我先讲这个展厅最好玩的展品？"
                    if exhibits else
                    "要不要我直接带你去？"
                ),
                classic=(
                    "抵达之后，可要我先讲彼处最值得先看的一件器物？"
                    if exhibits else
                    "可要在下继续引路？"
                ),
            ),
            suggested_actions=_route_actions(zone_name, exhibits, is_child, is_classic),
        )

    if exhibit_name and exhibit_name != "未确定" and guide_stage in {
        STAGE_EXHIBIT_OVERVIEW,
        STAGE_EXHIBIT_FOCUS,
        STAGE_EXHIBIT_DETAIL,
    }:
        return InitiativePlan(
            next_step_type=(
                "deepen_exhibit"
                if guide_stage in {STAGE_EXHIBIT_OVERVIEW, STAGE_EXHIBIT_FOCUS}
                else ("recommend_exhibit" if next_unseen_exhibit else "deepen_exhibit")
            ),
            next_step_target=next_unseen_exhibit or exhibit_name,
            follow_up_prompt=_cn_prompt(
                is_child,
                is_classic,
                regular=(
                    "您想先看这件展品的关键细节，还是听它背后的来历？"
                    if guide_stage in {STAGE_EXHIBIT_OVERVIEW, STAGE_EXHIBIT_FOCUS}
                    else (
                        f"您想继续深挖，还是看{next_unseen_exhibit}？"
                        if next_unseen_exhibit else
                        "这个展厅已经看完了，您要不要去下一个展厅？"
                    )
                ),
                child=(
                    "你想先看这件展品最特别的细节，还是听它的小故事？"
                    if guide_stage in {STAGE_EXHIBIT_OVERVIEW, STAGE_EXHIBIT_FOCUS}
                    else (
                        f"你还想继续深挖，还是去看{next_unseen_exhibit}？"
                        if next_unseen_exhibit else
                        "这个展厅已经看完了，你要不要去下一个展厅？"
                    )
                ),
                classic=(
                    "诸位是想先细看此物一处精妙，还是追溯它的来历？"
                    if guide_stage in {STAGE_EXHIBIT_OVERVIEW, STAGE_EXHIBIT_FOCUS}
                    else (
                        f"诸位还想细究此物，还是移步去看{next_unseen_exhibit}？"
                        if next_unseen_exhibit else
                        "此厅诸物已尽览，可要移步下一展厅？"
                    )
                ),
            ),
            suggested_actions=_exhibit_actions(
                exhibit_name,
                next_unseen_exhibit,
                next_unseen_zone,
                guide_stage,
                is_child,
                is_classic,
            ),
        )

    if zone_name and zone_name not in {"前台服务区", "卫生间"}:
        zone = _get_zone_by_name(domain_cfg, zone_name)
        exhibits = zone.get("exhibits", [])
        actions = _zone_actions(
            result,
            zone_name,
            exhibits,
            next_unseen_exhibit,
            next_unseen_zone,
            domain_cfg,
            is_child,
            is_classic,
        )
        next_type = "recommend_exhibit" if next_unseen_exhibit else "transition_zone"
        next_target = next_unseen_exhibit or next_unseen_zone or zone_name
        return InitiativePlan(
            next_step_type=next_type,
            next_step_target=next_target,
            follow_up_prompt=_cn_prompt(
                is_child,
                is_classic,
                regular=(
                    f"您想先听这个展厅的整体看点，还是我直接带您看还没讲过的{next_unseen_exhibit}？"
                    if next_unseen_exhibit else
                    "这个展厅已经看完了，您要不要去下一个展厅？"
                ),
                child=(
                    f"你想先听这个展厅有什么好看，还是我带你去看还没讲过的{next_unseen_exhibit}？"
                    if next_unseen_exhibit else
                    "这个展厅已经看完了，你要不要去下一个展厅？"
                ),
                classic=(
                    f"诸位愿先听此厅整体看点，还是移步去看尚未讲过的{next_unseen_exhibit}？"
                    if next_unseen_exhibit else
                    "此厅已尽览，可要移步下一展厅？"
                ),
            ),
            suggested_actions=actions,
        )

    first_zone = _get_first_primary_zone_name(domain_cfg)
    return InitiativePlan(
        next_step_type="ask_zone",
        next_step_target=first_zone,
        follow_up_prompt=_cn_prompt(
            is_child,
            is_classic,
            regular="您想让我先推荐一个起点吗？",
            child="要不要我先帮你选个起点？",
            classic="可要我先为诸位择一处起点？",
        ),
        suggested_actions=dedupe_actions([
            _action("推荐起点", f"请推荐一个适合开始了解的展区，比如{first_zone}。"),
            _action("轻松逛一圈", "请给我安排一条轻松一点的参观路线。"),
            _action("看代表展品", "请推荐一件最能代表这个馆的展品。"),
        ]),
    )


def _opening_actions(
    result: Dict[str, Any],
    domain_cfg: Dict[str, Any],
    is_child: bool,
    is_classic: bool,
) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    for zone in _unseen_primary_opening_zones(result, domain_cfg):
        zone_name = str(zone.get("name", "")).strip()
        if not zone_name:
            continue
        if is_child:
            actions.append(_action(_short_zone_label(zone_name), f"带我去看看{zone_name}。"))
        elif is_classic:
            actions.append(_action(_short_zone_label(zone_name), f"请先带我看看{zone_name}。"))
        else:
            actions.append(_action(_short_zone_label(zone_name), f"带我去{zone_name}。"))
    actions.append(
        _action(
            "你来推荐" if not is_classic else "烦请推荐",
            "你推荐我先看哪里？" if is_child else "请推荐一个最适合先看的展区。",
        )
    )
    return dedupe_actions(actions, limit=5)


def _opening_actions_en(domain_cfg: Dict[str, Any]) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    for zone in _primary_opening_zones(domain_cfg):
        zone_name = str(zone.get("name", "")).strip()
        if not zone_name:
            continue
        actions.append(_action(_short_zone_label(zone_name), f"Take me to the {zone_name}." ))
    actions.append(_action("Recommend one", "Recommend the best area to start with."))
    return dedupe_actions(actions, limit=5)


def _route_actions(
    zone_name: str,
    exhibits: List[Dict[str, Any]],
    is_child: bool,
    is_classic: bool,
) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    if is_child:
        actions.append(_action("直接带我去", "直接带我去下一个推荐点。"))
        if exhibits:
            actions.append(_action("到了先讲什么", f"到了{zone_name}先给我讲最好玩的展品。"))
        else:
            actions.append(_action("路上看什么", "路上有什么值得顺便看的？"))
        actions.append(_action("走简单一点", "给我一条更简单的路线。"))
        return dedupe_actions(actions)

    if is_classic:
        actions.append(_action("直接带我去", "请直接引我前往该展区。"))
        if exhibits:
            actions.append(_action("先讲代表展品", f"到了{zone_name}请先讲最值得一看的展品。"))
        else:
            actions.append(_action("路上顺便看什么", "途中还有何处值得顺便一观？"))
        actions.append(_action("换条近一点的路线", "请换一条更近一些的路线。"))
        return dedupe_actions(actions)

    actions.append(_action("直接带我去", "直接带我去下一个推荐展区。"))
    if exhibits:
        actions.append(_action("先讲重点展品", f"到了{zone_name}先给我讲重点展品。"))
    else:
        actions.append(_action("路上顺便看什么", "从这里过去路上有什么值得顺便看的？"))
    actions.append(_action("换条近一点的路线", "给我一条更近一些的路线。"))
    return dedupe_actions(actions)


def _route_actions_en(zone_name: str, exhibits: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = [
        _action("Guide me there", "Guide me to the next recommended stop."),
    ]
    if exhibits:
        actions.append(
            _action(
                "Introduce the key exhibit",
                f"When we arrive at the {zone_name}, introduce the key exhibit first.",
            )
        )
    else:
        actions.append(_action("Nearby highlight", "What should I notice on the way?"))
    actions.append(_action("Short route", "Give me a shorter route from here."))
    return dedupe_actions(actions)


def _exhibit_actions(
    exhibit_name: str,
    next_unseen_exhibit: str,
    next_unseen_zone: str,
    guide_stage: str,
    is_child: bool,
    is_classic: bool,
) -> List[Dict[str, str]]:
    if guide_stage == STAGE_EXHIBIT_FOCUS:
        if is_child:
            return dedupe_actions([
                _action("讲解细节", f"讲讲{exhibit_name}最特别的细节。"),
                _action("下一个", _next_target_text(next_unseen_exhibit, next_unseen_zone)),
            ], limit=2)
        if is_classic:
            return dedupe_actions([
                _action("讲解细节", f"请细讲{exhibit_name}最精妙之处。"),
                _action("下一个", _next_target_text(next_unseen_exhibit, next_unseen_zone, classic=True)),
            ], limit=2)
        return dedupe_actions([
            _action("讲解细节", f"请继续讲讲{exhibit_name}的细节。"),
            _action("下一个", _next_target_text(next_unseen_exhibit, next_unseen_zone)),
        ], limit=2)

    if is_child:
        actions = [
            _action("讲个小故事", f"给我讲讲{exhibit_name}背后的小故事。"),
            _action("看细节", f"{exhibit_name}最值得看的细节是什么？"),
        ]
        if next_unseen_exhibit:
            actions.append(_action(f"看{next_unseen_exhibit}", f"带我看看{next_unseen_exhibit}。"))
        elif next_unseen_zone:
            actions.append(_action("去下一站", f"带我去{next_unseen_zone}。"))
        else:
            actions.append(_action("下一个看什么", "接下来我还可以看什么？"))
        return dedupe_actions(actions, limit=2 if guide_stage == STAGE_EXHIBIT_DETAIL else 3)
    if is_classic:
        actions = [
            _action("细看此物", f"请再细讲{exhibit_name}的精妙之处。"),
            _action("追溯背景", f"请讲讲{exhibit_name}所处的时代背景。"),
        ]
        if next_unseen_exhibit:
            actions.append(_action(f"移步{next_unseen_exhibit}", f"请带我去看看{next_unseen_exhibit}。"))
        elif next_unseen_zone:
            actions.append(_action("继续前行", f"请引我前往{next_unseen_zone}。"))
        else:
            actions.append(_action("继续前行", "接下来可引我去看何物？"))
        return dedupe_actions(actions, limit=2 if guide_stage == STAGE_EXHIBIT_DETAIL else 3)
    actions = [
        _action("继续讲细节", f"请继续讲讲{exhibit_name}的细节。"),
        _action("讲历史背景", f"请介绍一下{exhibit_name}的历史背景。"),
    ]
    if next_unseen_exhibit:
        actions.append(_action(f"下一件：{next_unseen_exhibit}", f"带我看看{next_unseen_exhibit}。"))
    elif next_unseen_zone:
        actions.append(_action("去下一站", f"带我去{next_unseen_zone}。"))
    else:
        actions.append(_action("推荐下一件", "再推荐一件值得接着看的展品。"))
    return dedupe_actions(actions, limit=2 if guide_stage == STAGE_EXHIBIT_DETAIL else 3)


def _zone_actions(
    result: Dict[str, Any],
    zone_name: str,
    exhibits: List[Dict[str, Any]],
    next_unseen_exhibit: str,
    next_unseen_zone: str,
    domain_cfg: Dict[str, Any],
    is_child: bool,
    is_classic: bool,
) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    zone = _get_zone_by_name(domain_cfg, zone_name) if zone_name else {}
    unseen_zone_exhibits = _unseen_zone_exhibits(result, domain_cfg, zone_name)
    for exhibit in unseen_zone_exhibits:
        target_name = str(exhibit.get("name", "")).strip()
        if not target_name:
            continue
        if is_child:
            actions.append(_action(_short_exhibit_label(target_name), f"带我看看{target_name}。"))
        elif is_classic:
            actions.append(_action(_short_exhibit_label(target_name), f"请重点介绍{target_name}。"))
        else:
            actions.append(_action(_short_exhibit_label(target_name), f"请介绍一下{target_name}。"))
    if is_child:
        actions.append(_action("你来推荐", f"你推荐我先看{zone_name}里还没看过的哪件展品？"))
    elif is_classic:
        actions.append(_action("你来推荐", f"请为我推荐{zone_name}里还没看过、最值得先看的一件。"))
    else:
        actions.append(_action("你来推荐", f"请推荐{zone_name}里还没看过、最值得先看的展品。"))
    if not unseen_zone_exhibits and next_unseen_zone:
        if is_child:
            actions.insert(0, _action("去下一站", f"带我去{next_unseen_zone}。"))
        elif is_classic:
            actions.insert(0, _action("移步下一厅", f"请引我前往{next_unseen_zone}。"))
        else:
            actions.insert(0, _action("去下一站", f"带我去{next_unseen_zone}。"))
    return dedupe_actions(actions, limit=max(1, len(unseen_zone_exhibits)) + 1)


def _next_unseen_exhibit(
    result: Dict[str, Any],
    domain_cfg: Dict[str, Any],
    zone_name: str,
    current_exhibit: str,
) -> str:
    if not zone_name:
        return ""
    zone = _get_zone_by_name(domain_cfg, zone_name)
    if not zone:
        return ""
    exhibit_progress = result.get("exhibit_progress", {}) or {}
    visited_exhibits = set(result.get("visited_exhibits", []) or [])
    for exhibit in zone.get("exhibits", []) or []:
        exhibit_name = str(exhibit.get("name", "")).strip()
        if not exhibit_name or exhibit_name == current_exhibit:
            continue
        status = str(exhibit_progress.get(exhibit_name, "unseen")).strip()
        if exhibit_name not in visited_exhibits and status in {"", "unseen"}:
            return exhibit_name
    for exhibit in zone.get("exhibits", []) or []:
        exhibit_name = str(exhibit.get("name", "")).strip()
        if not exhibit_name or exhibit_name == current_exhibit:
            continue
        status = str(exhibit_progress.get(exhibit_name, "unseen")).strip()
        if status in {"", "unseen"}:
            return exhibit_name
    return ""


def _next_unseen_zone(result: Dict[str, Any], domain_cfg: Dict[str, Any], current_zone: str) -> str:
    zone_progress = result.get("zone_progress", {}) or {}
    visited_zones = set(result.get("visited_zones", []) or [])
    for zone in domain_cfg.get("zones", []):
        zone_name = str(zone.get("name", "")).strip()
        if not zone_name or zone_name == current_zone or zone.get("category") == "facility":
            continue
        status = str(zone_progress.get(zone_name, "unseen")).strip()
        if zone_name not in visited_zones and status in {"", "unseen"}:
            return zone_name
    for zone in domain_cfg.get("zones", []):
        zone_name = str(zone.get("name", "")).strip()
        if not zone_name or zone_name == current_zone or zone.get("category") == "facility":
            continue
        status = str(zone_progress.get(zone_name, "unseen")).strip()
        if status in {"", "unseen"}:
            return zone_name
    return ""


def _primary_opening_zones(domain_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    preferred_ids = [
        "zone_chinese_origins",
        "zone_calligraphy_painting",
        "zone_world_classics",
        "zone_children_exploration",
    ]
    zone_map = {str(zone.get("id", "")): zone for zone in domain_cfg.get("zones", [])}
    result: List[Dict[str, Any]] = []
    for zone_id in preferred_ids:
        zone = zone_map.get(zone_id)
        if zone:
            result.append(zone)
    return result


def _unseen_primary_opening_zones(result: Dict[str, Any], domain_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    unseen_names = {
        str(zone.get("name", "")).strip()
        for zone in _primary_opening_zones(domain_cfg)
        if str(zone.get("name", "")).strip()
    }
    visited_zones = set(result.get("visited_zones", []) or [])
    zone_progress = result.get("zone_progress", {}) or {}
    unseen: List[Dict[str, Any]] = []
    fallback: List[Dict[str, Any]] = []
    for zone in _primary_opening_zones(domain_cfg):
        zone_name = str(zone.get("name", "")).strip()
        if not zone_name:
            continue
        fallback.append(zone)
        status = str(zone_progress.get(zone_name, "unseen")).strip()
        if zone_name not in visited_zones and status in {"", "unseen"}:
            unseen.append(zone)
    return unseen or fallback


def _unseen_zone_exhibits(
    result: Dict[str, Any],
    domain_cfg: Dict[str, Any],
    zone_name: str,
) -> List[Dict[str, Any]]:
    zone = _get_zone_by_name(domain_cfg, zone_name)
    if not zone:
        return []
    exhibit_progress = result.get("exhibit_progress", {}) or {}
    visited_exhibits = set(result.get("visited_exhibits", []) or [])
    unseen: List[Dict[str, Any]] = []
    for exhibit in zone.get("exhibits", []) or []:
        exhibit_name = str(exhibit.get("name", "")).strip()
        if not exhibit_name:
            continue
        status = str(exhibit_progress.get(exhibit_name, "unseen")).strip()
        if exhibit_name not in visited_exhibits and status in {"", "unseen"}:
            unseen.append(exhibit)
    return unseen


def _short_zone_label(zone_name: str) -> str:
    replacements = {
        "中华文明源流展区": "文明源流",
        "中国书画与文人精神展区": "书画文人",
        "世界文明经典展区": "世界经典",
        "儿童探索与互动体验区": "互动体验",
    }
    return replacements.get(zone_name, zone_name.replace("展区", "").replace("体验区", "体验"))


def _short_exhibit_label(exhibit_name: str) -> str:
    for token in ["（复制件）", "（复制）", "（摹本）"]:
        exhibit_name = exhibit_name.replace(token, "")
    return exhibit_name


def _next_target_text(next_unseen_exhibit: str, next_unseen_zone: str, classic: bool = False) -> str:
    if next_unseen_exhibit:
        return f"带我看看{next_unseen_exhibit}。" if not classic else f"请带我去看看{next_unseen_exhibit}。"
    if next_unseen_zone:
        return f"带我去{next_unseen_zone}。" if not classic else f"请引我前往{next_unseen_zone}。"
    return "推荐下一件值得接着看的展品。"


def _field(result: Dict[str, Any], key: str) -> str:
    return str(result.get(key, "")).strip()


def _get_zone_by_name(domain_cfg: Dict[str, Any], zone_name: str) -> Dict[str, Any]:
    for zone in domain_cfg.get("zones", []):
        if zone.get("name") == zone_name:
            return zone
    return {}


def _get_first_primary_zone_name(domain_cfg: Dict[str, Any]) -> str:
    for zone in domain_cfg.get("zones", []):
        if zone.get("category") != "facility":
            return str(zone.get("name", "")).strip() or "中华文明源流展区"
    return "中华文明源流展区"


def _action(label: str, text: str) -> Dict[str, str]:
    return {"label": label, "text": text}


def _persona_requires_english(persona_id: str) -> bool:
    return persona_id.startswith("eu_")


def _has_question(text: str) -> bool:
    return any(mark in text for mark in ["?", "？"])


def _is_english_text(text: str) -> bool:
    return not any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _cn_prompt(
    is_child: bool,
    is_classic: bool,
    *,
    regular: str,
    child: str,
    classic: str,
) -> str:
    if is_child:
        return child
    if is_classic:
        return classic
    return regular
