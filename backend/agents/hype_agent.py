"""Hype agent: drafts a short chat message + reaction emoji using research data.

Rate-limited to once per 30s per session.
"""

from __future__ import annotations

import json
import logging
import os

from google import genai
from google.genai import types

from backend.storage import firestore_client as store

log = logging.getLogger(__name__)

MODEL = "gemini-3.5-flash"
COOLDOWN_SECONDS = 30.0

_genai: genai.Client | None = None


def client() -> genai.Client:
    global _genai
    if _genai is None:
        _genai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _genai


HYPE_PROMPT = """You are the Hype Agent in a Google Meet. Your job is to drop ONE short,
high-energy chat message that references the fact below, plus one emoji reaction.

Topic: {topic}
Fact: {summary}

Hard rules:
- Chat line: <= 90 characters, conversational, no hashtags, no "as a fan of"
- Reaction emoji: exactly one of: 👍 ❤️ 😂 🎉 👏 🔥
- If the fact is empty or weak, return empty chat (the orchestrator will skip)

Return JSON:
{{"chat": "<line or empty>", "emoji": "<emoji>"}}
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "chat": {"type": "string"},
        "emoji": {"type": "string"},
    },
    "required": ["chat", "emoji"],
}

ALLOWED_EMOJIS = {"👍", "❤️", "😂", "🎉", "👏", "🔥"}


def run(sid: str, research_data: dict) -> None:
    topic = (research_data or {}).get("topic", "").strip()
    summary = (research_data or {}).get("summary", "").strip()
    if not topic or not summary:
        return

    if not store.agent_cooldown_ok(sid, "hype_agent", COOLDOWN_SECONDS):
        log.debug("[hype] skipped (cooldown)")
        return

    prompt = HYPE_PROMPT.format(topic=topic, summary=summary)

    try:
        resp = client().models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=OUTPUT_SCHEMA,
                temperature=0.7,
            ),
        )
        parsed = json.loads(resp.text)
    except Exception as e:
        log.warning("hype agent gemini call failed: %s", e)
        return

    chat = (parsed.get("chat") or "").strip()
    emoji = (parsed.get("emoji") or "").strip()

    if chat:
        if store.enqueue_chat(sid, chat, "hype_agent"):
            store.log_incident(
                sid,
                agent="hype_agent",
                action="enqueued_chat",
                reason=f"topic={topic!r}",
                severity="info",
                extra={"chat": chat},
            )
            log.info("[hype] chat queued: %s", chat)
    if emoji in ALLOWED_EMOJIS:
        if store.enqueue_reaction(sid, emoji, "hype_agent"):
            store.log_incident(
                sid,
                agent="hype_agent",
                action="enqueued_reaction",
                reason=f"topic={topic!r}",
                severity="info",
                extra={"emoji": emoji},
            )
            log.info("[hype] reaction queued: %s", emoji)
