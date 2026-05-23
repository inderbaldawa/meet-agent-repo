"""Research agent: given a topic from the Context agent, web-search and summarize.

Writes to `sessions/{sid}.research_data`. Caches per-topic for 5 minutes.
"""

from __future__ import annotations

import json
import logging
import os

from google import genai
from google.genai import types

from backend.storage import firestore_client as store
from backend.tools import google_search

log = logging.getLogger(__name__)

MODEL = "gemini-3.1-pro"

_genai: genai.Client | None = None


def client() -> genai.Client:
    global _genai
    if _genai is None:
        _genai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _genai


SUMMARIZE_PROMPT = """You are the Research Agent for an AI assistant in a meeting.
The current topic is: {topic}

Below are web search snippets. Distil ONE concrete, surprising or useful fact a host
could share in chat to keep viewers engaged. Keep it under 25 words. Avoid generic
trivia. If snippets are uninformative, return an empty summary.

Snippets:
{snippets}

Return JSON only:
{{"summary": "<the fact, or empty string>", "citations": [<urls>]}}
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "citations"],
}


def run(sid: str, shared_context: dict) -> None:
    topic = (shared_context or {}).get("topic", "").strip()
    if not topic:
        return

    th = store.topic_hash(topic)
    cached = store.get_research_cache(sid, th)
    if cached:
        store.update_research_data(sid, cached)
        store.log_incident(
            sid,
            agent="research_agent",
            action="cache_hit",
            reason=f"topic={topic!r}",
            severity="info",
        )
        return

    hits = google_search.search(topic, num=3)
    if not hits:
        store.log_incident(
            sid,
            agent="research_agent",
            action="no_results",
            reason=f"topic={topic!r}",
            severity="warning",
        )
        return

    snippet_block = "\n".join(f"- {h['title']}: {h['snippet']} ({h['link']})" for h in hits)
    prompt = SUMMARIZE_PROMPT.format(topic=topic, snippets=snippet_block)

    try:
        resp = client().models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=OUTPUT_SCHEMA,
                temperature=0.4,
            ),
        )
        parsed = json.loads(resp.text)
    except Exception as e:
        log.warning("research agent gemini call failed: %s", e)
        return

    payload = {
        "topic": topic,
        "summary": parsed.get("summary", ""),
        "citations": parsed.get("citations", []),
    }
    if not payload["summary"]:
        return

    store.set_research_cache(sid, th, payload)
    store.update_research_data(sid, payload)
    store.log_incident(
        sid,
        agent="research_agent",
        action="researched",
        reason=f"topic={topic!r}",
        severity="info",
        extra={"summary": payload["summary"]},
    )
    log.info("[research] %s -> %s", topic, payload["summary"][:80])
