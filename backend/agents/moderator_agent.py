"""Moderator: watches chat_message events for emoji spam, posts a single warning.

Rate-limited to once per 60s.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.storage import firestore_client as store

log = logging.getLogger(__name__)

COOLDOWN_SECONDS = 15.0
EMOJI_SPAM_THRESHOLD = 3

_EMOJI_RANGES = (
    (0x2600, 0x27BF),
    (0x1F300, 0x1FAFF),
    (0x1F900, 0x1F9FF),
)


def _count_emojis(text: str) -> int:
    return sum(1 for ch in text if any(lo <= ord(ch) <= hi for lo, hi in _EMOJI_RANGES))


def run(sid: str, event: dict[str, Any]) -> None:
    if event.get("type") != "chat_message":
        return
    data = event.get("data") or {}
    text = data.get("text") or ""
    sender = data.get("sender") or "unknown"

    # Trust an upstream is_spam flag if present, else recompute
    is_spam = bool(data.get("is_spam")) or _count_emojis(text) >= EMOJI_SPAM_THRESHOLD
    if not is_spam:
        return

    if not store.agent_cooldown_ok(sid, "moderator_agent", COOLDOWN_SECONDS):
        log.debug("[moderator] spam detected but cooldown active")
        return

    # Find the most-spammed emoji in the message for a specific callout
    from collections import Counter
    emoji_counts = Counter(ch for ch in text if ord(ch) > 0x1F300)
    top_emoji = emoji_counts.most_common(1)[0][0] if emoji_counts else ""
    name = sender.split()[0] if sender and sender != "unknown" else "Hey"
    warning = (
        f"⚠️ {name}, lay off the {top_emoji} — keep chat readable for everyone."
        if top_emoji
        else f"⚠️ {name}, too many emojis — keep chat readable please."
    )

    if store.enqueue_chat(sid, warning, "moderator_agent"):
        store.log_incident(
            sid,
            agent="moderator_agent",
            action="warned_spam",
            reason=f"emoji_count exceeded threshold by {sender}",
            severity="warning",
            extra={"sender": sender, "sample": text[:120]},
        )
        log.info("[moderator] warned spam from %s", sender)
