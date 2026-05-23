"""Expert Commentator Agent: watches the game screen and drops insightful tips,
strategy advice, or fun facts grounded in what's actually visible.

Cooldown: 45s. Only fires when a specific game/activity is detected (urgency >= 0.5).
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
COOLDOWN_SECONDS = 45.0

SKIP_TOPICS = {
    "idle", "technology", "display", "screen", "screenshot", "computing",
    "software", "hardware", "interface", "computer", "device", "monitor",
    "google meet", "google", "meet", "zoom", "teams", "microsoft teams",
    "video conference", "video call", "conference", "webex", "skype",
    "usb", "bluetooth", "webcam", "microphone", "lobby", "waiting room",
}

_genai: genai.Client | None = None


def client() -> genai.Client:
    global _genai
    if _genai is None:
        _genai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _genai


PROMPT = """You are an Expert Commentator on a live game stream. You have just seen a screenshot
of what's being played/shown. Your job: deliver ONE sharp, specific insight — a strategy tip,
a surprising fact, or a technique observation — grounded in what's actually visible.

Topic detected: {topic}
Vision labels: {labels}
On-screen text: {text}

Rules:
- Be specific to the game/content — no generic advice
- Max 90 characters, conversational, no hashtags
- If there's nothing specific enough to comment on, return empty chat
- Do NOT comment on the stream setup, camera, or UI

Return JSON: {{"chat": "<insight or empty string>"}}
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"chat": {"type": "string"}},
    "required": ["chat"],
}


def run(sid: str, event: dict[str, Any], shared_context: dict | None = None) -> None:
    if event.get("type") != "screen_analysis":
        return

    topic = (shared_context or {}).get("topic", "").strip()
    urgency = (shared_context or {}).get("urgency", 0.0)

    if not topic or topic == "idle" or urgency < 0.5:
        return

    if any(skip in topic.lower() for skip in SKIP_TOPICS):
        return

    if not store.agent_cooldown_ok(sid, "expert_commentator_agent", COOLDOWN_SECONDS):
        return

    data = event.get("data", {})
    labels = data.get("labels", [])
    text = (data.get("text") or "")[:300]

    prompt = PROMPT.format(
        topic=topic,
        labels=", ".join(labels[:8]) or "(none)",
        text=text or "(none)",
    )

    try:
        resp = client().models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=OUTPUT_SCHEMA,
                temperature=0.5,
            ),
        )
        parsed = json.loads(resp.text)
    except Exception as e:
        log.warning("expert commentator gemini call failed: %s", e)
        return

    chat = (parsed.get("chat") or "").strip()
    if not chat:
        return

    if store.enqueue_chat(sid, chat, "expert_commentator_agent"):
        store.log_incident(
            sid,
            agent="expert_commentator_agent",
            action="commented",
            reason=f"topic={topic!r}",
            severity="info",
            extra={"chat": chat},
        )
        log.info("[expert] %s", chat)
