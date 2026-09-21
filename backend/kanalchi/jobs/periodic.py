"""Periodic tasks. procrastinate dedupes periodic runs across workers via the `timestamp` argument."""

from __future__ import annotations

from kanalchi.core.logging import get_logger
from kanalchi.core.redis import get_redis
from kanalchi.jobs.app import app

log = get_logger(__name__)


@app.periodic(cron="* * * * *")
@app.task(queue="index", name="periodic.heartbeat", pass_context=True)
async def heartbeat(context, timestamp: int) -> None:  # noqa: ANN001
    """Cheap liveness signal for the index worker; the telegram worker writes its own heartbeat in-process."""
    await get_redis().set("hb:worker-index", str(timestamp), ex=180)
