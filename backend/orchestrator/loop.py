"""Per-session capture loops: screen vision capture + chat-message capture."""

from __future__ import annotations

import asyncio
import hashlib
import logging

from backend.bot.meet_bot import MeetBot
from backend.storage import firestore_client as store
from backend.vision import labeler

log = logging.getLogger(__name__)

CAPTURE_INTERVAL_SECONDS = 3.0
CHAT_POLL_SECONDS = 4.0


async def capture_loop(sid: str, bot: MeetBot, stop_event: asyncio.Event) -> None:
    """Run until `stop_event` is set. Errors are logged but don't stop the loop unless fatal."""
    log.info("[loop] starting capture loop for session=%s", sid)
    consecutive_failures = 0
    while not stop_event.is_set():
        try:
            png = await bot.take_screenshot()
            vision_result = await asyncio.to_thread(labeler.analyze, png)
            store.append_event(
                sid,
                {
                    "type": "screen_analysis",
                    "data": {
                        "labels": vision_result["labels"],
                        "text": vision_result["text"],
                        "logos": vision_result["logos"],
                    },
                },
            )
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            log.warning("[loop] capture error (%d in a row): %s", consecutive_failures, e)
            if consecutive_failures >= 10:
                log.error("[loop] too many failures, exiting capture loop")
                return

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CAPTURE_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

    log.info("[loop] capture loop stopped for session=%s", sid)


def _emoji_count(text: str) -> int:
    return sum(1 for ch in text if ord(ch) > 0x1F300)


async def chat_monitor_loop(sid: str, bot: MeetBot, stop_event: asyncio.Event) -> None:
    """Poll Meet's chat panel periodically; emit `chat_message` events for new messages."""
    log.info("[chat] starting chat monitor for session=%s", sid)
    seen_ids: set[str] = set()
    while not stop_event.is_set():
        try:
            messages = await bot.get_chat_messages()
            for m in messages:
                msg_id = m.get("id") or ""
                text = (m.get("text") or "").strip()
                sender = (m.get("sender") or "").strip()
                if not text:
                    continue
                fingerprint = msg_id or hashlib.sha256(f"{sender}::{text}".encode()).hexdigest()[:16]
                if fingerprint in seen_ids:
                    continue
                seen_ids.add(fingerprint)
                emojis = _emoji_count(text)
                store.append_event(
                    sid,
                    {
                        "type": "chat_message",
                        "data": {
                            "text": text,
                            "sender": sender,
                            "emoji_count": emojis,
                            "is_spam": emojis > 5,
                        },
                    },
                )
        except Exception as e:
            log.warning("[chat] poll error: %s", e)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CHAT_POLL_SECONDS)
        except asyncio.TimeoutError:
            pass

    log.info("[chat] chat monitor stopped for session=%s", sid)
