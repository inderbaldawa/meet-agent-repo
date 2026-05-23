"""Drains the chat and reaction queues into actual bot actions.

A global 5s minimum spacing between any two bot actions prevents Meet from
flagging the account.
"""

from __future__ import annotations

import asyncio
import logging
import time

from backend.bot.meet_bot import MeetBot
from backend.storage import firestore_client as store

log = logging.getLogger(__name__)

GLOBAL_ACTION_FLOOR_SECONDS = 0.5
TICK_SECONDS = 1.0


async def drainer_loop(sid: str, bot: MeetBot, stop_event: asyncio.Event) -> None:
    log.info("[drainer] starting for session=%s", sid)
    last_action_ts = 0.0
    while not stop_event.is_set():
        try:
            if time.time() - last_action_ts >= GLOBAL_ACTION_FLOOR_SECONDS:
                chat_item = await asyncio.to_thread(store.drain_chat, sid)
                if chat_item:
                    msg = chat_item.get("message", "")
                    agent = chat_item.get("agent", "?")
                    if msg:
                        await bot.send_chat(msg)
                        last_action_ts = time.time()
                        log.info("[drainer] chat from %s: %s", agent, msg[:80])
                else:
                    react_item = await asyncio.to_thread(store.drain_reaction, sid)
                    if react_item:
                        emoji = react_item.get("emoji", "")
                        agent = react_item.get("agent", "?")
                        if emoji:
                            await bot.send_reaction(emoji)
                            last_action_ts = time.time()
                            log.info("[drainer] reaction from %s: %s", agent, emoji)
        except Exception as e:
            log.warning("[drainer] error: %s", e)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_SECONDS)
        except asyncio.TimeoutError:
            pass

    log.info("[drainer] stopped for session=%s", sid)
