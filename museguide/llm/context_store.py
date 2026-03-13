import threading
import time
from typing import Any, Dict, List


class ContextStore:
    """
    In-memory session store keyed by (session_id, persona_id).
    Keeps a compact tour state plus a short rolling dialogue history.
    """

    def __init__(self, ttl_seconds: int = 1200, max_chars: int = 280, max_turns: int = 6):
        self._ttl = ttl_seconds
        self._max_chars = max_chars
        self._max_turns = max_turns
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._zone_status_order = {
            "unseen": 0,
            "entered": 1,
            "overview": 2,
            "detailed": 3,
        }
        self._exhibit_status_order = {
            "unseen": 0,
            "brief": 1,
            "detailed": 2,
        }

    def _key(self, session_id: str, persona_id: str) -> str:
        return f"{session_id}::{persona_id}"

    def _trim(self, text: str) -> str:
        if not text:
            return ""
        text = " ".join(text.strip().split())
        if len(text) <= self._max_chars:
            return text
        return text[: self._max_chars].rstrip() + "…"

    def _empty_state(self) -> Dict[str, Any]:
        return {
            "updated_at": time.time(),
            "turns": [],
            "current_zone": "",
            "current_exhibit": "",
            "current_focus_status": "",
            "guide_stage": "",
            "reply_text": "",
            "follow_up_text": "",
            "pending_action_label": "",
            "pending_action_text": "",
            "pending_action_type": "",
            "pending_action_target": "",
            "visited_zones": [],
            "visited_exhibits": [],
            "zone_progress": {},
            "exhibit_progress": {},
            "user_interests": [],
            "tour_event": "",
        }

    def _get_state_locked(self, key: str) -> Dict[str, Any]:
        now = time.time()
        state = self._data.get(key)
        if not state:
            state = self._empty_state()
            self._data[key] = state
            return state
        if now - float(state.get("updated_at", 0)) > self._ttl:
            state = self._empty_state()
            self._data[key] = state
        return state

    @staticmethod
    def _dedupe(items: List[str]) -> List[str]:
        result: List[str] = []
        seen: set[str] = set()
        for item in items:
            value = str(item or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    @staticmethod
    def _merge_status_maps(
        existing: Dict[str, str],
        updates: Dict[str, str],
        order: Dict[str, int],
    ) -> Dict[str, str]:
        merged = dict(existing or {})
        for key, status in (updates or {}).items():
            name = str(key or "").strip()
            value = str(status or "").strip()
            if not name or not value:
                continue
            old_value = str(merged.get(name, "")).strip()
            if order.get(value, -1) >= order.get(old_value, -1):
                merged[name] = value
        return merged

    def get(self, session_id: str, persona_id: str) -> str:
        if not session_id:
            return ""
        key = self._key(session_id, persona_id)
        with self._lock:
            state = dict(self._get_state_locked(key))
            turns = list(state.get("turns", []))

        lines: List[str] = []
        current_zone = self._trim(state.get("current_zone", ""))
        current_exhibit = self._trim(state.get("current_exhibit", ""))
        current_focus_status = self._trim(state.get("current_focus_status", ""))
        guide_stage = self._trim(state.get("guide_stage", ""))
        pending_action_label = self._trim(state.get("pending_action_label", ""))
        pending_action_text = self._trim(state.get("pending_action_text", ""))
        pending_action_type = self._trim(state.get("pending_action_type", ""))
        pending_action_target = self._trim(state.get("pending_action_target", ""))
        visited_zones = [self._trim(v) for v in state.get("visited_zones", [])[:4]]
        visited_exhibits = [self._trim(v) for v in state.get("visited_exhibits", [])[:4]]
        user_interests = [self._trim(v) for v in state.get("user_interests", [])[:4]]
        zone_progress = state.get("zone_progress", {}) or {}
        exhibit_progress = state.get("exhibit_progress", {}) or {}

        if current_zone or current_exhibit or guide_stage:
            lines.append("Current tour state:")
            if current_zone:
                lines.append(f"- Current zone: {current_zone}")
            if current_exhibit:
                lines.append(f"- Current exhibit: {current_exhibit}")
            if current_focus_status:
                lines.append(f"- Current focus status: {current_focus_status}")
            if guide_stage:
                lines.append(f"- Guide stage: {guide_stage}")
            if pending_action_label or pending_action_text:
                lines.append(
                    f"- Pending recommendation: {pending_action_label or pending_action_text}"
                )
            if pending_action_type or pending_action_target:
                lines.append(
                    f"- Pending action type: {pending_action_type or '未指定'}"
                    + (f" / target: {pending_action_target}" if pending_action_target else "")
                )

        if visited_zones:
            lines.append("Visited zones: " + " / ".join([v for v in visited_zones if v]))
        if visited_exhibits:
            lines.append("Visited exhibits: " + " / ".join([v for v in visited_exhibits if v]))
        if user_interests:
            lines.append("User interests: " + " / ".join([v for v in user_interests if v]))
        if zone_progress:
            compact_zone_progress = [
                f"{self._trim(name)}({self._trim(status)})"
                for name, status in list(zone_progress.items())[:6]
                if name and status
            ]
            if compact_zone_progress:
                lines.append("Zone progress: " + " / ".join(compact_zone_progress))
        if exhibit_progress:
            compact_exhibit_progress = [
                f"{self._trim(name)}({self._trim(status)})"
                for name, status in list(exhibit_progress.items())[:6]
                if name and status
            ]
            if compact_exhibit_progress:
                lines.append("Exhibit progress: " + " / ".join(compact_exhibit_progress))

        if turns:
            lines.append("Recent dialogue:")
            for turn in turns[-self._max_turns:]:
                user_text = self._trim(str(turn.get("user", "")))
                guide_text = self._trim(str(turn.get("guide", "")))
                if user_text:
                    lines.append(f"User: {user_text}")
                if guide_text:
                    lines.append(f"Guide: {guide_text}")

        return "\n".join(lines)

    def get_recent_dialogue(self, session_id: str, persona_id: str, max_turns: int = 3) -> str:
        if not session_id:
            return ""
        key = self._key(session_id, persona_id)
        with self._lock:
            state = dict(self._get_state_locked(key))
            turns = list(state.get("turns", []))

        if not turns:
            return ""

        lines: List[str] = ["最近对话："]
        for turn in turns[-max(1, max_turns):]:
            user_text = self._trim(str(turn.get("user", "")))
            guide_text = self._trim(str(turn.get("guide", "")))
            if user_text:
                lines.append(f"- 用户：{user_text}")
            if guide_text:
                lines.append(f"- 导览员：{guide_text}")
        return "\n".join(lines)

    def get_session_state(self, session_id: str, persona_id: str) -> Dict[str, Any]:
        if not session_id:
            return self._empty_state()
        key = self._key(session_id, persona_id)
        with self._lock:
            state = self._get_state_locked(key)
            return {
                "current_zone": state.get("current_zone", ""),
                "current_exhibit": state.get("current_exhibit", ""),
                "current_focus_status": state.get("current_focus_status", ""),
                "guide_stage": state.get("guide_stage", ""),
                "reply_text": state.get("reply_text", ""),
                "follow_up_text": state.get("follow_up_text", ""),
                "pending_action_label": state.get("pending_action_label", ""),
                "pending_action_text": state.get("pending_action_text", ""),
                "pending_action_type": state.get("pending_action_type", ""),
                "pending_action_target": state.get("pending_action_target", ""),
                "visited_zones": list(state.get("visited_zones", [])),
                "visited_exhibits": list(state.get("visited_exhibits", [])),
                "zone_progress": dict(state.get("zone_progress", {})),
                "exhibit_progress": dict(state.get("exhibit_progress", {})),
                "user_interests": list(state.get("user_interests", [])),
                "tour_event": state.get("tour_event", ""),
            }

    def update(
        self,
        session_id: str,
        persona_id: str,
        *,
        user_text: str,
        guide_text: str,
        current_zone: str = "",
        current_exhibit: str = "",
        current_focus_status: str = "",
        guide_stage: str = "",
        reply_text: str = "",
        follow_up_text: str = "",
        pending_action_label: str = "",
        pending_action_text: str = "",
        pending_action_type: str = "",
        pending_action_target: str = "",
        visited_zones: List[str] | None = None,
        visited_exhibits: List[str] | None = None,
        zone_progress: Dict[str, str] | None = None,
        exhibit_progress: Dict[str, str] | None = None,
        user_interests: List[str] | None = None,
        tour_event: str = "",
    ) -> Dict[str, Any]:
        if not session_id:
            return {
                "current_zone": current_zone or "",
                "current_exhibit": current_exhibit or "",
                "current_focus_status": current_focus_status or "",
                "guide_stage": guide_stage or "",
                "reply_text": reply_text or "",
                "follow_up_text": follow_up_text or "",
                "pending_action_label": pending_action_label or "",
                "pending_action_text": pending_action_text or "",
                "pending_action_type": pending_action_type or "",
                "pending_action_target": pending_action_target or "",
                "visited_zones": self._dedupe(visited_zones or []),
                "visited_exhibits": self._dedupe(visited_exhibits or []),
                "zone_progress": dict(zone_progress or {}),
                "exhibit_progress": dict(exhibit_progress or {}),
                "user_interests": self._dedupe(user_interests or []),
                "tour_event": tour_event or "",
            }

        key = self._key(session_id, persona_id)
        with self._lock:
            state = self._get_state_locked(key)
            turns = list(state.get("turns", []))
            turns.append({
                "user": user_text or "",
                "guide": guide_text or "",
            })
            state["turns"] = turns[-self._max_turns:]
            state["current_zone"] = current_zone or state.get("current_zone", "")
            state["current_exhibit"] = current_exhibit or ""
            state["current_focus_status"] = current_focus_status or state.get("current_focus_status", "")
            state["guide_stage"] = guide_stage or state.get("guide_stage", "")
            state["reply_text"] = reply_text or ""
            state["follow_up_text"] = follow_up_text or ""
            state["pending_action_label"] = pending_action_label or ""
            state["pending_action_text"] = pending_action_text or ""
            state["pending_action_type"] = pending_action_type or ""
            state["pending_action_target"] = pending_action_target or ""
            state["visited_zones"] = self._dedupe(
                list(state.get("visited_zones", [])) + list(visited_zones or [])
            )
            state["visited_exhibits"] = self._dedupe(
                list(state.get("visited_exhibits", [])) + list(visited_exhibits or [])
            )
            state["zone_progress"] = self._merge_status_maps(
                state.get("zone_progress", {}),
                zone_progress or {},
                self._zone_status_order,
            )
            state["exhibit_progress"] = self._merge_status_maps(
                state.get("exhibit_progress", {}),
                exhibit_progress or {},
                self._exhibit_status_order,
            )
            state["user_interests"] = self._dedupe(
                list(state.get("user_interests", [])) + list(user_interests or [])
            )
            state["tour_event"] = tour_event or state.get("tour_event", "")
            state["updated_at"] = time.time()
            return {
                "current_zone": state["current_zone"],
                "current_exhibit": state["current_exhibit"],
                "current_focus_status": state["current_focus_status"],
                "guide_stage": state["guide_stage"],
                "reply_text": state["reply_text"],
                "follow_up_text": state["follow_up_text"],
                "pending_action_label": state["pending_action_label"],
                "pending_action_text": state["pending_action_text"],
                "pending_action_type": state["pending_action_type"],
                "pending_action_target": state["pending_action_target"],
                "visited_zones": list(state["visited_zones"]),
                "visited_exhibits": list(state["visited_exhibits"]),
                "zone_progress": dict(state["zone_progress"]),
                "exhibit_progress": dict(state["exhibit_progress"]),
                "user_interests": list(state["user_interests"]),
                "tour_event": state["tour_event"],
            }

    def set_pending_recommendation(
        self,
        session_id: str,
        persona_id: str,
        *,
        reply_text: str = "",
        follow_up_text: str = "",
        pending_action_label: str = "",
        pending_action_text: str = "",
        pending_action_type: str = "",
        pending_action_target: str = "",
    ) -> Dict[str, Any]:
        if not session_id:
            return {
                "reply_text": reply_text or "",
                "follow_up_text": follow_up_text or "",
                "pending_action_label": pending_action_label or "",
                "pending_action_text": pending_action_text or "",
                "pending_action_type": pending_action_type or "",
                "pending_action_target": pending_action_target or "",
            }

        key = self._key(session_id, persona_id)
        with self._lock:
            state = self._get_state_locked(key)
            state["reply_text"] = reply_text or state.get("reply_text", "")
            state["follow_up_text"] = follow_up_text or ""
            state["pending_action_label"] = pending_action_label or ""
            state["pending_action_text"] = pending_action_text or ""
            state["pending_action_type"] = pending_action_type or ""
            state["pending_action_target"] = pending_action_target or ""
            state["updated_at"] = time.time()
            return {
                "reply_text": state["reply_text"],
                "follow_up_text": state["follow_up_text"],
                "pending_action_label": state["pending_action_label"],
                "pending_action_text": state["pending_action_text"],
                "pending_action_type": state["pending_action_type"],
                "pending_action_target": state["pending_action_target"],
            }
