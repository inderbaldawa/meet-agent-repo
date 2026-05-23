"""Heartbeat agent: guarantees the bot produces output every 10s.

When a real topic is known, 40% of the time it generates a short context-aware
comment via Gemini. Otherwise it enqueues a random reaction emoji.
Falls back to reaction on any LLM error.
"""

from __future__ import annotations

import json
import logging
import os
import random

from google import genai
from google.genai import types

from backend.storage import firestore_client as store

log = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"
REACTIONS = ["👍", "❤️", "😂", "🎉", "👏", "🔥"]

SKIP_TOPICS = {
    "idle", "technology", "display", "screen", "screenshot", "computing",
    "software", "hardware", "interface", "computer", "device", "monitor",
    "google meet", "google", "meet", "zoom", "teams", "microsoft teams",
    "video conference", "video call", "conference", "webex", "skype",
    "usb", "bluetooth", "webcam", "microphone", "lobby", "waiting room",
}

PROMPT = """You are a viewer watching a live stream. Based on the topic and summary,
write ONE short viewer comment — ≤ 50 characters. Be direct, specific, factual.
No hype, no jokes, no hashtags, no "great point!", no sycophantic openers.

Topic: {topic}
Summary: {summary}

Return JSON: {{"comment": "<text or empty string>"}}"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"comment": {"type": "string"}},
    "required": ["comment"],
}

_genai: genai.Client | None = None


def _client() -> genai.Client:
    global _genai
    if _genai is None:
        _genai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _genai


def run(sid: str) -> None:
    sess = (store.session_ref(sid).get().to_dict()) or {}
    shared = sess.get("shared_context") or {}
    research = sess.get("research_data") or {}

    topic = (shared.get("topic") or "").strip()
    summary = (research.get("summary") or "").strip()

    has_real_topic = (
        topic
        and topic != "idle"
        and not any(s in topic.lower() for s in SKIP_TOPICS)
        and len(summary) >= 20
    )

    # Always enqueue a reaction for guaranteed activity
    emoji = random.choice(REACTIONS)
    store.enqueue_reaction(sid, emoji, "heartbeat_agent")
    log.info("[heartbeat] reaction: %s", emoji)

    # Also try to enqueue a comment when context is available
    if has_real_topic:
        try:
            resp = _client().models.generate_content(
                model=MODEL,
                contents=PROMPT.format(topic=topic, summary=summary[:200]),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=OUTPUT_SCHEMA,
                    temperature=0.5,
                ),
            )
            comment = (json.loads(resp.text).get("comment") or "").strip()
            if comment and len(comment) <= 90:
                if store.enqueue_chat(sid, comment, "heartbeat_agent"):
                    store.log_incident(
                        sid, "heartbeat_agent", "commented",
                        f"topic={topic!r}", "info", {"comment": comment},
                    )
                    log.info("[heartbeat] comment: %s", comment)
        except Exception as e:
            log.warning("[heartbeat] gemini comment failed: %s", e)
