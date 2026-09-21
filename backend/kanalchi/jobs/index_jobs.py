"""Jobs executed inside worker-index (Phase 2 fills these in: embeddings, extraction, mapping)."""

from __future__ import annotations

from kanalchi.core.logging import get_logger
from kanalchi.jobs.app import app

log = get_logger(__name__)


@app.task(queue="index", name="index.ping")
async def ping(payload: str = "pong") -> str:
    log.info("index.ping", payload=payload)
    return payload


@app.task(queue="index", name="index.post", retry=1)
async def index_post(post_id: int) -> None:
    log.debug("index.post.noop", post_id=post_id)


@app.task(queue="index", name="index.backlog", retry=0)
async def index_backlog(tenant_id: int) -> None:
    log.info("index.backlog.noop", tenant_id=tenant_id)
