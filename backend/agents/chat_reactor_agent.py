"""Chat reactor agent: reacts to participant chat messages with emoji reactions
and/or short replies.

Rate-limited to once per 15s. Skips the bot's own messages and spam.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from google import genai
from google.genai import types

from backend.storage import firestore_client as store

log = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"
COOLDOWN_SECONDS = 15.0
ALLOWED_EMOJIS = {"👍", "❤️", "😂", "🎉", "👏", "🔥"}

_genai: genai.Client | None = None


def client() -> genai.Client:
    global _genai
    if _genai is None:
        _genai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _genai


PROMPT = """You are the Chat Reactor in a Google Meet. A participant posted a chat message.
Decide whether to react with an emoji, send a brief reply, or do nothing.

Message from {sender}: "{text}"

Rules:
- React if the message is interesting, enthusiastic, funny, or on-topic
- Reply (≤ 60 chars) only if they asked a question or said something worth engaging with
- Do NOTHING for mundane filler: "ok", "nice", "lol", "👍", "cool", single words
- Reaction emoji must be exactly one of: 👍 ❤️ 😂 🎉 👏 🔥
- No hashtags, no "as an AI", keep replies conversational and brief

Return JSON: {{"reaction": "<emoji or empty string>", "reply": "<text or empty string>"}}
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "reaction": {"type": "string"},
        "reply": {"type": "string"},
    },
    "required": ["reaction", "reply"],
}


def run(sid: str, event: dict[str, Any], bot_display_name: str = "AI Assistant") -> None:
    if event.get("type") != "chat_message":
        return

    data = event.get("data") or {}
    text = (data.get("text") or "").strip()
    sender = (data.get("sender") or "").strip()

    if not text or not sender:
        return

    if sender.lower() == bot_display_name.lower():
        return

    if data.get("is_spam"):
        return

    if not store.agent_cooldown_ok(sid, "chat_reactor_agent", COOLDOWN_SECONDS):
        log.debug("[reactor] skipped (cooldown)")
        return

    prompt = PROMPT.format(sender=sender, text=text)

    try:
        resp = client().models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=OUTPUT_SCHEMA,
                temperature=0.6,
            ),
        )
        parsed = json.loads(resp.text)
    except Exception as e:
        log.warning("chat reactor gemini call failed: %s", e)
        return

    reaction = (parsed.get("reaction") or "").strip()
    reply = (parsed.get("reply") or "").strip()

    if reaction in ALLOWED_EMOJIS:
        if store.enqueue_reaction(sid, reaction, "chat_reactor_agent"):
            store.log_incident(
                sid,
                agent="chat_reactor_agent",
                action="reacted",
                reason=f"{sender!r}: {text[:60]}",
                severity="info",
                extra={"reaction": reaction},
            )
            log.info("[reactor] %s → %s", sender, reaction)

    if reply:
        if store.enqueue_chat(sid, reply, "chat_reactor_agent"):
            store.log_incident(
                sid,
                agent="chat_reactor_agent",
                action="replied",
                reason=f"{sender!r}: {text[:60]}",
                severity="info",
                extra={"reply": reply},
            )
            log.info("[reactor] replied to %s: %s", sender, reply)
