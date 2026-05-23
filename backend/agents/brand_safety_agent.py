"""Brand Safety Agent: scans Vision AI output for content that could create
brand or legal risk — copyrighted logos, sensitive brands, inappropriate content.

Logs warnings to the dashboard. Only posts in chat for high-severity issues.
Cooldown: 30s.
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
COOLDOWN_SECONDS = 8.0

_genai: genai.Client | None = None


def client() -> genai.Client:
    global _genai
    if _genai is None:
        _genai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _genai


PROMPT = """You are a Brand Safety Agent reviewing a screenshot from a live stream.

Check for:
- Logos of competitors, controversial brands, or brands with strict streaming policies
- Text suggesting copyrighted music or licensed content is playing
- Any content that could get the stream flagged or demonetised

Vision labels: {labels}
Detected logos: {logos}
On-screen text snippet: {text}

Return JSON:
{{
  "issue": "none|copyright|brand|content",
  "severity": "none|low|high",
  "detail": "<one-line description or empty>",
  "warn_chat": "<brief warning ≤ 70 chars if severity=high, else empty>"
}}
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "issue": {"type": "string", "enum": ["none", "copyright", "brand", "content"]},
        "severity": {"type": "string", "enum": ["none", "low", "high"]},
        "detail": {"type": "string"},
        "warn_chat": {"type": "string"},
    },
    "required": ["issue", "severity", "detail", "warn_chat"],
}


def run(sid: str, event: dict[str, Any]) -> None:
    if event.get("type") != "screen_analysis":
        return

    data = event.get("data", {})
    labels = data.get("labels", [])
    logos = data.get("logos", [])
    text = (data.get("text") or "")[:200]

    if not labels and not logos and not text:
        return

    if not store.agent_cooldown_ok(sid, "brand_safety_agent", COOLDOWN_SECONDS):
        return

    prompt = PROMPT.format(
        labels=", ".join(labels[:10]) or "(none)",
        logos=", ".join(logos) or "(none)",
        text=text or "(none)",
    )

    try:
        resp = client().models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=OUTPUT_SCHEMA,
                temperature=0.1,
            ),
        )
        parsed = json.loads(resp.text)
    except Exception as e:
        log.warning("brand safety gemini call failed: %s", e)
        return

    severity = parsed.get("severity", "none")
    if severity == "none":
        return

    issue = parsed.get("issue", "")
    detail = parsed.get("detail", "")
    warn_chat = (parsed.get("warn_chat") or "").strip()

    store.log_incident(
        sid,
        agent="brand_safety_agent",
        action=f"flagged_{issue}",
        reason=detail,
        severity="warning" if severity == "low" else "critical",
    )
    log.warning("[brand_safety] %s (%s): %s", issue, severity, detail)

    if warn_chat and severity == "high":
        if store.enqueue_chat(sid, warn_chat, "brand_safety_agent"):
            log.info("[brand_safety] warned: %s", warn_chat)
