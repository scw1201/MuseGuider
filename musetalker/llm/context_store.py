import threading
import time
from typing import Dict, Tuple


class ContextStore:
    """
    Simple in-memory last-turn cache keyed by (session_id, persona_id).
    Keeps only the latest user+guide pair with TTL to avoid unbounded growth.
    """

    def __init__(self, ttl_seconds: int = 600, max_chars: int = 280):
        self._ttl = ttl_seconds
        self._max_chars = max_chars
        self._lock = threading.Lock()
        self._data: Dict[str, Tuple[float, str, str, str]] = {}

    def _key(self, session_id: str, persona_id: str) -> str:
        return f"{session_id}::{persona_id}"

    def _trim(self, text: str) -> str:
        if not text:
            return ""
        text = " ".join(text.strip().split())
        if len(text) <= self._max_chars:
            return text
        return text[: self._max_chars].rstrip() + "…"

    def get(self, session_id: str, persona_id: str) -> str:
        if not session_id:
            return ""
        key = self._key(session_id, persona_id)
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if not item:
                return ""
            ts, user_text, guide_text, location_text = item
            if now - ts > self._ttl:
                self._data.pop(key, None)
                return ""
        user_text = self._trim(user_text)
        guide_text = self._trim(guide_text)
        if not user_text or not guide_text:
            return ""
        lines = [
            "Previous turn (last turn only):",
            f"User: {user_text}",
            f"Guide: {guide_text}",
        ]
        if location_text:
            lines.append(f"Location: {location_text}")
        return "\n".join(lines)

    def set(
        self,
        session_id: str,
        persona_id: str,
        user_text: str,
        guide_text: str,
        location_text: str = "",
    ) -> None:
        if not session_id:
            return
        key = self._key(session_id, persona_id)
        with self._lock:
            self._data[key] = (
                time.time(),
                user_text or "",
                guide_text or "",
                location_text or "",
            )
