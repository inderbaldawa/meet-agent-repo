"""All Firestore I/O lives here.

Document layout:
    sessions/{sid}                          # session metadata + shared_context + research_data
        events/{auto}                       # vision/chat/system events from the bot
        incidents/{auto}                    # structured agent decisions for the dashboard
        chat_queue/{deterministic-id}       # outgoing chat messages, drained by bot
        reaction_queue/{deterministic-id}   # outgoing reaction emojis, drained by bot
        agent_state/{agent_id}              # per-agent cooldown / last_emit_ts
        research_cache/{topic_hash}         # 5-minute cache of research results
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1 import transactional

log = logging.getLogger(__name__)

_client: firestore.Client | None = None


def client() -> firestore.Client:
    """Lazy singleton. Uses GOOGLE_APPLICATION_CREDENTIALS env var implicitly."""
    global _client
    if _client is None:
        project = os.environ.get("GCP_PROJECT_ID")
        database = os.environ.get("FIRESTORE_DATABASE", "(default)")
        _client = firestore.Client(project=project, database=database)
    return _client


def session_ref(sid: str) -> firestore.DocumentReference:
    return client().collection("sessions").document(sid)


def create_session(meet_url: str, display_name: str) -> str:
    sid = uuid.uuid4().hex[:12]
    session_ref(sid).set(
        {
            "meet_url": meet_url,
            "display_name": display_name,
            "status": "active",
            "shared_context": {},
            "research_data": {},
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )
    log.info("created session %s for %s", sid, meet_url)
    return sid


def append_event(sid: str, payload: dict[str, Any]) -> str:
    _, ref = session_ref(sid).collection("events").add(
        {**payload, "timestamp": firestore.SERVER_TIMESTAMP}
    )
    return ref.id


def update_shared_context(sid: str, ctx: dict[str, Any]) -> None:
    session_ref(sid).update({"shared_context": ctx, "shared_context_at": firestore.SERVER_TIMESTAMP})


def update_research_data(sid: str, data: dict[str, Any]) -> None:
    session_ref(sid).update({"research_data": data, "research_data_at": firestore.SERVER_TIMESTAMP})


def _deterministic_id(agent_id: str, content: str) -> str:
    return hashlib.sha256(f"{agent_id}::{content}".encode()).hexdigest()[:24]


def enqueue_chat(sid: str, message: str, agent_id: str) -> bool:
    """Returns True if enqueued, False if a duplicate of a pending message."""
    doc_id = _deterministic_id(agent_id, f"chat::{message}")
    ref = session_ref(sid).collection("chat_queue").document(doc_id)
    if ref.get().exists:
        return False
    ref.set(
        {
            "message": message,
            "agent": agent_id,
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )
    return True


def enqueue_reaction(sid: str, emoji: str, agent_id: str) -> bool:
    doc_id = _deterministic_id(agent_id, f"react::{emoji}::{int(time.time() // 10)}")
    ref = session_ref(sid).collection("reaction_queue").document(doc_id)
    if ref.get().exists:
        return False
    ref.set(
        {
            "emoji": emoji,
            "agent": agent_id,
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )
    return True


@transactional
def _drain_one(txn, queue_ref: firestore.CollectionReference) -> dict[str, Any] | None:
    docs = list(queue_ref.order_by("timestamp").limit(1).stream(transaction=txn))
    if not docs:
        return None
    doc = docs[0]
    data = doc.to_dict() or {}
    data["_id"] = doc.id
    txn.delete(doc.reference)
    return data


def drain_chat(sid: str) -> dict[str, Any] | None:
    return _drain_one(client().transaction(), session_ref(sid).collection("chat_queue"))


def drain_reaction(sid: str) -> dict[str, Any] | None:
    return _drain_one(client().transaction(), session_ref(sid).collection("reaction_queue"))


def agent_cooldown_ok(sid: str, agent_id: str, seconds: float) -> bool:
    """Returns True if the agent's last_emit_ts is older than `seconds` ago (or never set).
    On success, updates last_emit_ts to now. Best-effort, not strictly atomic."""
    ref = session_ref(sid).collection("agent_state").document(agent_id)
    snap = ref.get()
    now = time.time()
    if snap.exists:
        last = (snap.to_dict() or {}).get("last_emit_ts", 0)
        if now - last < seconds:
            return False
    ref.set({"last_emit_ts": now, "updated_at": firestore.SERVER_TIMESTAMP})
    return True


def log_incident(
    sid: str,
    agent: str,
    action: str,
    reason: str,
    severity: str = "info",
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "agent": agent,
        "action": action,
        "reason": reason,
        "severity": severity,
        "timestamp": firestore.SERVER_TIMESTAMP,
    }
    if extra:
        payload["extra"] = extra
    session_ref(sid).collection("incidents").add(payload)


def get_research_cache(sid: str, topic_hash: str, ttl_seconds: float = 300) -> dict[str, Any] | None:
    ref = session_ref(sid).collection("research_cache").document(topic_hash)
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    cached_at = data.get("cached_at_epoch", 0)
    if time.time() - cached_at > ttl_seconds:
        return None
    return data.get("payload")


def set_research_cache(sid: str, topic_hash: str, payload: dict[str, Any]) -> None:
    session_ref(sid).collection("research_cache").document(topic_hash).set(
        {"payload": payload, "cached_at_epoch": time.time(), "cached_at": firestore.SERVER_TIMESTAMP}
    )


def topic_hash(topic: str) -> str:
    return hashlib.sha256(topic.strip().lower().encode()).hexdigest()[:16]


def get_last_event_timestamp(sid: str, event_type: str) -> float | None:
    """Return the epoch timestamp of the most recent event of a given type, or None."""
    docs = list(
        session_ref(sid)
        .collection("events")
        .where("type", "==", event_type)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )
    if not docs:
        return None
    ts = (docs[0].to_dict() or {}).get("timestamp")
    return ts.timestamp() if ts and hasattr(ts, "timestamp") else None
