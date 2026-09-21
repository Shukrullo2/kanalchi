"""Jobs executed inside worker-index."""

from __future__ import annotations

from kanalchi.core.logging import get_logger
from kanalchi.jobs.app import app

log = get_logger(__name__)


@app.task(queue="index", name="index.ping")
async def ping(payload: str = "pong") -> str:
    log.info("index.ping", payload=payload)
    return payload
