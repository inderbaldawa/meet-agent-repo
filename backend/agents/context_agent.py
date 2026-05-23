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

MODEL = "gemini-3.5-flash"

_genai: genai.Client | None = None


def client() -> genai.Client:
    global _genai
    if _genai is None:
        _genai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _genai


PROMPT_TEMPLATE = """You are the Context Agent for an AI assistant observing a Google Meet.
You receive snapshots of what the meeting's screen-share is showing, distilled into vision labels,
detected text, and detected logos.

Decide what the meeting is currently ABOUT in one short topic phrase. Pick a sentiment.
Pick an urgency 0.0-1.0 for whether the other agents should react soon.

Latest vision labels: {labels}
Detected text (truncated): {text}
Detected logos: {logos}

Return JSON only, schema:
{{"topic": "<3-6 words>", "sentiment": "positive|neutral|negative", "urgency": <float 0-1>}}
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
