"""Context agent: takes a screen-analysis event, distills it into a topic + sentiment + urgency.

Writes to `sessions/{sid}.shared_context`. Other agents listen for changes on that field.
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

_genai: genai.Client | None = None


def client() -> genai.Client:
    global _genai
    if _genai is None:
        _genai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _genai


PROMPT_TEMPLATE = """You are the Context Agent for an AI assistant observing a live game stream in Google Meet.
You receive Vision AI output from a screenshot: labels, on-screen text, and logos.

Your job: identify what game or real-world activity is actually being shown.

Rules:
- If you see a video conferencing UI (Google Meet, Zoom, Teams lobby, waiting room, participant
  tiles, camera feeds, chat panels, toolbar buttons) → return topic "idle" and urgency 0.0
- If labels are generic tech/UI (display, screenshot, gadget, font, software, computer monitor,
  technology, multimedia, electronic device, USB, Bluetooth device) → return topic "idle" urgency 0.0
- Only return a real topic when you can identify something specific that is being SHARED or
  shown intentionally: a game title, a physical object, a book cover, a sport, a dish, a slide deck
  with real content, code, etc.
- urgency 0.0-0.4 = background/ambient, 0.5-0.7 = something interesting, 0.8-1.0 = act now

Latest vision labels: {labels}
Detected text (truncated): {text}
Detected logos: {logos}

Return JSON only:
{{"topic": "<3-6 words or 'idle'>", "sentiment": "positive|neutral|negative", "urgency": <float 0-1>}}
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "urgency": {"type": "number"},
    },
    "required": ["topic", "sentiment", "urgency"],
}


def run(sid: str, event: dict[str, Any]) -> None:
    """Process one screen_analysis event into a topic update."""
    if event.get("type") != "screen_analysis":
        return

    data = event.get("data", {})
    labels = data.get("labels", [])
    text = (data.get("text") or "")[:400]
    logos = data.get("logos", [])

    if not labels and not text:
        return

    # Skip if all labels are generic Meet/webcam noise
    GENERIC = {
        "face", "head", "person", "forehead", "chin", "selfie", "hair", "nose",
        "display device", "screenshot", "technology", "gadget", "font",
        "electronic device", "multimedia", "computer monitor", "software",
        "smile", "skin", "neck", "communication", "video call", "videotelephony",
        "collaboration", "web conferencing", "product", "service",
    }
    if labels and all(l.lower() in GENERIC for l in labels):
        return

    prompt = PROMPT_TEMPLATE.format(
        labels=", ".join(labels) or "(none)",
        text=text or "(none)",
        logos=", ".join(logos) or "(none)",
    )

    try:
        resp = client().models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=OUTPUT_SCHEMA,
                temperature=0.2,
            ),
        )
        parsed = json.loads(resp.text)
    except Exception as e:
        log.warning("context agent gemini call failed: %s", e)
        return

    store.update_shared_context(sid, parsed)
    store.log_incident(
        sid,
        agent="context_agent",
        action="updated_context",
        reason=f"topic={parsed.get('topic')!r} sentiment={parsed.get('sentiment')}",
        severity="info",
        extra=parsed,
    )
    log.info("[context] %s", parsed)
