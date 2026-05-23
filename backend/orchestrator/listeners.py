"""Firestore on_snapshot listeners that drive the agents.

Each listener dispatches an agent's `run()` into a ThreadPoolExecutor so the
Firestore callback never blocks.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from google.cloud.firestore_v1.watch import Watch

from backend.agents import context_agent, hype_agent, moderator_agent, research_agent
from backend.storage import firestore_client as store

log = logging.getLogger(__name__)


class SessionListeners:
    """Owns the on_snapshot watchers for one session. Call stop() on shutdown."""

    def __init__(self, sid: str, max_workers: int = 4) -> None:
        self.sid = sid
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"agent-{sid}")
        self._watches: list[Watch] = []
        self._seen_event_ids: set[str] = set()
        self._last_shared_context: dict | None = None
        self._last_research_data: dict | None = None

    def start(self) -> None:
        sess_ref = store.session_ref(self.sid)
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
                self._submit(context_agent.run, self.sid, payload)
            elif evt_type == "chat_message":
                self._submit(moderator_agent.run, self.sid, payload)

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
                self._submit(hype_agent.run, self.sid, research)

    def stop(self) -> None:
        for w in self._watches:
            try:
                w.unsubscribe()
            except Exception:
                pass
        self.executor.shutdown(wait=False, cancel_futures=True)
        log.info("[listeners] stopped for session=%s", self.sid)
