"""Firestore on_snapshot listeners that drive all six agents.

Each listener dispatches agent run() calls into a ThreadPoolExecutor so the
Firestore callback never blocks.

Agent routing:
  screen_analysis  → context_agent, expert_commentator_agent,
                     controversy_detector_agent, brand_safety_agent,
                     engagement_optimizer_agent
  chat_message     → moderator_agent, chat_reactor_agent,
                     controversy_detector_agent
  shared_context ↑ → research_agent
  research_data  ↑ → hype_agent
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from google.cloud.firestore_v1.watch import Watch

from backend.agents import (
    brand_safety_agent,
    chat_reactor_agent,
    context_agent,
    controversy_detector_agent,
    engagement_optimizer_agent,
    expert_commentator_agent,
    hype_agent,
    moderator_agent,
    research_agent,
)
from backend.storage import firestore_client as store

log = logging.getLogger(__name__)


class SessionListeners:
    """Owns the on_snapshot watchers for one session. Call stop() on shutdown."""

    def __init__(self, sid: str, max_workers: int = 8) -> None:
        self.sid = sid
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"agent-{sid}")
        self._watches: list[Watch] = []
        self._seen_event_ids: set[str] = set()
        self._last_shared_context: dict | None = None
        self._last_research_data: dict | None = None
        self._bot_display_name: str = "AI Assistant"

    def start(self) -> None:
        sess_ref = store.session_ref(self.sid)
        sess_doc = sess_ref.get()
        self._bot_display_name = (sess_doc.to_dict() or {}).get("display_name", "AI Assistant")

        events_ref = sess_ref.collection("events")
        self._watches.append(events_ref.on_snapshot(self._on_events))
        self._watches.append(sess_ref.on_snapshot(self._on_session_doc))
        log.info("[listeners] started for session=%s", self.sid)

    def _submit(self, fn: Callable, *args) -> None:
        def wrapped() -> None:
            try:
                fn(*args)
            except Exception as e:
                log.exception("[listeners] agent threw: %s", e)
        self.executor.submit(wrapped)

    def _on_events(self, col_snapshot, changes, read_time) -> None:
        for change in changes:
            if change.type.name != "ADDED":
                continue
            doc_id = change.document.id
            if doc_id in self._seen_event_ids:
                continue
            self._seen_event_ids.add(doc_id)
            payload = change.document.to_dict() or {}
            evt_type = payload.get("type")

            if evt_type == "screen_analysis":
                ctx = self._last_shared_context
                self._submit(context_agent.run, self.sid, payload)
                self._submit(expert_commentator_agent.run, self.sid, payload, ctx)
                self._submit(controversy_detector_agent.run, self.sid, payload)
                self._submit(brand_safety_agent.run, self.sid, payload)
                self._submit(engagement_optimizer_agent.run, self.sid, payload, ctx)

            elif evt_type == "chat_message":
                self._submit(moderator_agent.run, self.sid, payload)
                self._submit(chat_reactor_agent.run, self.sid, payload, self._bot_display_name)
                self._submit(controversy_detector_agent.run, self.sid, payload)

    def _on_session_doc(self, doc_snapshot, changes, read_time) -> None:
        for snap in doc_snapshot:
            data = snap.to_dict() or {}
            shared = data.get("shared_context")
            research = data.get("research_data")
            if shared and shared != self._last_shared_context:
                self._last_shared_context = shared
                self._submit(research_agent.run, self.sid, shared)
            if research and research != self._last_research_data:
                self._last_research_data = research
                self._submit(hype_agent.run, self.sid, research, self._last_shared_context)

    def stop(self) -> None:
        for w in self._watches:
            try:
                w.unsubscribe()
            except Exception:
                pass
        self.executor.shutdown(wait=False, cancel_futures=True)
        log.info("[listeners] stopped for session=%s", self.sid)
