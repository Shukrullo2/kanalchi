"""Jobs executed inside worker-publish."""

from __future__ import annotations

from kanalchi.core.logging import get_logger
from kanalchi.jobs.app import app

log = get_logger(__name__)


@app.task(queue="publish", name="publish.ping")
async def ping(payload: str = "pong") -> str:
    log.info("publish.ping", payload=payload)
    return payload
