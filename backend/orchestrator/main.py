"""FastAPI orchestrator.

POST /deploy {meet_url, display_name} -> {session_id}
GET  /session/{sid} -> current state
DELETE /session/{sid} -> graceful shutdown
GET  /health
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.bot.meet_bot import MeetBot
from backend.orchestrator.drainer import drainer_loop
from backend.orchestrator.listeners import SessionListeners
from backend.orchestrator.loop import capture_loop, chat_monitor_loop, heartbeat_loop
from backend.storage import firestore_client as store

dotenv.load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("orchestrator")


class ActiveSession:
    def __init__(self, sid: str, bot: MeetBot) -> None:
        self.sid = sid
        self.bot = bot
        self.stop_event = asyncio.Event()
        self.tasks: list[asyncio.Task] = []
        self.listeners: SessionListeners | None = None


_sessions: dict[str, ActiveSession] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for sid in list(_sessions):
        await _shutdown_session(sid)


app = FastAPI(lifespan=lifespan)

origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not origins:
    origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):\d+$",
    allow_methods=["*"],
    allow_headers=["*"],
)


class DeployRequest(BaseModel):
    meet_url: str
    display_name: str = "AI Assistant"
    agenda: str = ""


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "active_sessions": list(_sessions.keys())}


@app.post("/deploy")
async def deploy(req: DeployRequest) -> dict[str, Any]:
    sid = store.create_session(req.meet_url, req.display_name, req.agenda)

    bot = MeetBot(req.meet_url, req.display_name)
    await bot.start()

    try:
        await bot.join()
    except Exception as e:
        log.exception("bot failed to join: %s", e)
        await bot.stop()
        store.log_incident(sid, "system", "join_failed", str(e), "critical")
        raise HTTPException(status_code=504, detail=f"bot failed to join meeting: {e}")

    session = ActiveSession(sid, bot)
    _sessions[sid] = session

    listeners = SessionListeners(sid)
    listeners.start()
    session.listeners = listeners

    session.tasks.append(asyncio.create_task(capture_loop(sid, bot, session.stop_event)))
    session.tasks.append(asyncio.create_task(chat_monitor_loop(sid, bot, session.stop_event)))
    session.tasks.append(asyncio.create_task(drainer_loop(sid, bot, session.stop_event)))
    session.tasks.append(asyncio.create_task(heartbeat_loop(sid, session.stop_event)))

    store.log_incident(sid, "system", "session_started", req.meet_url, "info")
    return {"session_id": sid, "status": "active"}


@app.get("/session/{sid}")
def get_session(sid: str) -> dict[str, Any]:
    snap = store.session_ref(sid).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="session not found")
    return {"id": sid, **(snap.to_dict() or {})}


@app.delete("/session/{sid}")
async def stop_session(sid: str) -> dict[str, Any]:
    if sid not in _sessions:
        raise HTTPException(status_code=404, detail="session not active in this orchestrator")
    await _shutdown_session(sid)
    return {"status": "stopped", "session_id": sid}


async def _shutdown_session(sid: str) -> None:
    session = _sessions.pop(sid, None)
    if session is None:
        return
    session.stop_event.set()
    for t in session.tasks:
        try:
            await asyncio.wait_for(t, timeout=10.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            t.cancel()
    if session.listeners is not None:
        session.listeners.stop()
    try:
        await session.bot.leave()
    finally:
        await session.bot.stop()
    store.session_ref(sid).update({"status": "stopped"})
    store.log_incident(sid, "system", "session_stopped", "graceful", "info")
