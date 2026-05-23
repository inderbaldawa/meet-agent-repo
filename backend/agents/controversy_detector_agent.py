"""Controversy Detector Agent: scans screen text and chat messages for risky content.

When something risky is detected it logs a warning incident and, if urgent,
diplomatically changes the subject in chat.

Cooldown: 60s (shared across screen and chat triggers).
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
COOLDOWN_SECONDS = 60.0

_genai: genai.Client | None = None


def client() -> genai.Client:
    global _genai
    if _genai is None:
        _genai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _genai


SCREEN_PROMPT = """You are a Controversy Detector monitoring a live stream for risky content.

Analyse what's visible on screen. Flag only genuine risks:
- Explicit political debate or divisive topics
- Personal information accidentally shown (email, phone, address)
- Potentially illegal content
- Content that could violate platform terms of service

Vision labels: {labels}
On-screen text: {text}

Return JSON:
{{
  "risk_level": "none|low|high",
  "reason": "<brief description or empty>",
  "redirect_chat": "<diplomatic subject-change message ≤ 80 chars, or empty>"
}}
"""

CHAT_PROMPT = """You are a Controversy Detector monitoring a live stream chat for risky content.

Message from {sender}: "{text}"

Flag only genuine risks: hate speech, doxxing, TOS violations, dangerous content.
Ignore edgy humour, mild profanity, or off-topic comments.

Return JSON:
{{
  "risk_level": "none|low|high",
  "reason": "<brief description or empty>",
  "redirect_chat": "<diplomatic response ≤ 80 chars, or empty>"
}}
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_level": {"type": "string", "enum": ["none", "low", "high"]},
        "reason": {"type": "string"},
        "redirect_chat": {"type": "string"},
    },
    "required": ["risk_level", "reason", "redirect_chat"],
}


def _evaluate(prompt: str) -> dict | None:
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
        return json.loads(resp.text)
    except Exception as e:
        log.warning("controversy detector gemini call failed: %s", e)
        return None


def run(sid: str, event: dict[str, Any]) -> None:
    evt_type = event.get("type")
    data = event.get("data", {})

    if evt_type == "screen_analysis":
        labels = data.get("labels", [])
        text = (data.get("text") or "")[:400]
        if not text and not labels:
            return
        prompt = SCREEN_PROMPT.format(
            labels=", ".join(labels[:10]) or "(none)",
            text=text or "(none)",
        )
    elif evt_type == "chat_message":
        text = (data.get("text") or "").strip()
        sender = (data.get("sender") or "unknown").strip()
        if not text:
            return
        prompt = CHAT_PROMPT.format(sender=sender, text=text)
    else:
        return

    if not store.agent_cooldown_ok(sid, "controversy_detector_agent", COOLDOWN_SECONDS):
        return

    result = _evaluate(prompt)
    if not result:
        return

    risk = result.get("risk_level", "none")
    if risk == "none":
        return

    reason = result.get("reason", "")
    redirect = (result.get("redirect_chat") or "").strip()
    severity = "critical" if risk == "high" else "warning"

    store.log_incident(
        sid,
        agent="controversy_detector_agent",
        action="risk_detected",
        reason=reason,
        severity=severity,
    )
    log.warning("[controversy] %s risk: %s", risk, reason)

    if redirect and risk == "high":
        if store.enqueue_chat(sid, redirect, "controversy_detector_agent"):
            log.info("[controversy] redirecting: %s", redirect)
