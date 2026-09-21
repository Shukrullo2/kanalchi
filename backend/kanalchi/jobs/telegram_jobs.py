"""Jobs executed inside worker-telegram (the only process that owns Telethon clients)."""

from __future__ import annotations

from kanalchi.core.logging import get_logger
from kanalchi.jobs.app import app

log = get_logger(__name__)


@app.task(queue="telegram", name="telegram.ping")
async def ping(payload: str = "pong") -> str:
    log.info("telegram.ping", payload=payload)
    return payload
