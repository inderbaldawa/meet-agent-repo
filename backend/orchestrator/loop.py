"""Per-session capture loops: screen vision capture + chat-message capture."""

from __future__ import annotations

import asyncio
import hashlib
import logging

from backend.agents import heartbeat_agent
from backend.bot.meet_bot import MeetBot
from backend.storage import firestore_client as store
from backend.vision import labeler

log = logging.getLogger(__name__)

CAPTURE_INTERVAL_SECONDS = 1.5
CHAT_POLL_SECONDS = 1.5


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
    # Unicode emoji ranges: Misc Symbols (2600-26FF), Dingbats (2700-27BF),
    # Supplemental Symbols (1F300+), and variation selectors/ZWJ sequences.
    emoji_ranges = (
        (0x2600, 0x27BF),   # Misc Symbols & Dingbats (❤️, ⭐, ✅, etc.)
        (0x1F300, 0x1FAFF), # Emoji block (😀, 🎉, 👍, 🔥, etc.)
        (0x1F900, 0x1F9FF), # Supplemental Symbols
    )
    return sum(1 for ch in text if any(lo <= ord(ch) <= hi for lo, hi in emoji_ranges))


EMOJI_SPAM_THRESHOLD = 3


async def chat_monitor_loop(sid: str, bot: MeetBot, stop_event: asyncio.Event) -> None:
    """Poll Meet's chat panel periodically; emit `chat_message` events for new messages."""
    log.info("[chat] starting chat monitor for session=%s", sid)

    # Open chat panel immediately so get_chat_messages() can read messages.
    # Retry a few times since Meet UI may still be loading.
    for attempt in range(5):
        try:
            await bot._open_chat_panel()
            log.info("[chat] chat panel opened")
            break
        except Exception as e:
            log.warning("[chat] panel open attempt %d failed: %s", attempt + 1, e)
            await asyncio.sleep(3)

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
                            "is_spam": emojis >= EMOJI_SPAM_THRESHOLD,
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


HEARTBEAT_INTERVAL_SECONDS = 5.0
HEARTBEAT_WARMUP_SECONDS = 5.0


async def heartbeat_loop(sid: str, stop_event: asyncio.Event) -> None:
    """Guarantees the bot produces at least one action every 10s."""
    log.info("[heartbeat] starting for session=%s", sid)

    # Let capture + context pipeline initialize before the first heartbeat.
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_WARMUP_SECONDS)
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            await asyncio.to_thread(heartbeat_agent.run, sid)
        except Exception as e:
            log.warning("[heartbeat] error: %s", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

    log.info("[heartbeat] stopped for session=%s", sid)
