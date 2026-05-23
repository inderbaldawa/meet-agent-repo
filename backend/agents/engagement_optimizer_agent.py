"""Engagement Optimizer Agent: monitors chat activity and prompts interaction
when the stream goes quiet.

Fires on screen_analysis events. Checks how long it has been since the last
chat message — if silence exceeds SILENCE_THRESHOLD_SECONDS, it posts an
interactive prompt (poll suggestion, Q&A call, etc.).

Cooldown: 90s so it doesn't spam prompts.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from google import genai
from google.genai import types

from backend.storage import firestore_client as store

log = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"
COOLDOWN_SECONDS = 15.0
SILENCE_THRESHOLD_SECONDS = 15.0

_genai: genai.Client | None = None


def client() -> genai.Client:
    global _genai
    if _genai is None:
        _genai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _genai


PROMPT = """You are an Engagement Optimizer on a live stream. The chat has gone quiet for a while.
Suggest ONE short interactive prompt to re-engage the audience.

Current topic: {topic}
Stream agenda: {agenda}

Ideas (pick whichever fits best):
- A quick poll question related to the topic or agenda
- An open question to the audience ("What would YOU do here?")
- A challenge or call to action tied to what the streamer is doing
- A milestone tease ("We're close to 100 messages — let's go!")

Rules: ≤ 80 characters, energetic, no hashtags. Return empty if topic is idle/generic.

Return JSON: {{"chat": "<prompt or empty string>"}}
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"chat": {"type": "string"}},
    "required": ["chat"],
}


def run(sid: str, event: dict[str, Any], shared_context: dict | None = None) -> None:
    if event.get("type") != "screen_analysis":
        return

    topic = (shared_context or {}).get("topic", "idle").strip()
    if topic == "idle":
        return

    last_chat_ts = store.get_last_event_timestamp(sid, "chat_message")
    now = time.time()

    if last_chat_ts is not None and (now - last_chat_ts) < SILENCE_THRESHOLD_SECONDS:
        return

    if not store.agent_cooldown_ok(sid, "engagement_optimizer_agent", COOLDOWN_SECONDS):
        return

    agenda = (shared_context or {}).get("agenda", "")
    prompt = PROMPT.format(topic=topic, agenda=agenda or "not specified")

    try:
        resp = client().models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=OUTPUT_SCHEMA,
                temperature=0.8,
            ),
        )
        parsed = json.loads(resp.text)
    except Exception as e:
        log.warning("engagement optimizer gemini call failed: %s", e)
        return

    chat = (parsed.get("chat") or "").strip()
    if not chat:
        return

    if store.enqueue_chat(sid, chat, "engagement_optimizer_agent"):
        store.log_incident(
            sid,
            agent="engagement_optimizer_agent",
            action="prompted_engagement",
            reason=f"chat silent >{SILENCE_THRESHOLD_SECONDS:.0f}s, topic={topic!r}",
            severity="info",
            extra={"chat": chat},
        )
        log.info("[engagement] %s", chat)
