"""Periodic tasks. procrastinate dedupes periodic runs across workers via the `timestamp` argument."""

from __future__ import annotations

from sqlalchemy import select

from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, Tenant
from kanalchi.core.redis import get_redis
from kanalchi.jobs.app import app

log = get_logger(__name__)


@app.periodic(cron="* * * * *")
@app.task(queue="index", name="periodic.heartbeat", pass_context=True)
async def heartbeat(context, timestamp: int) -> None:  # noqa: ANN001
    await get_redis().set("hb:worker-index", str(timestamp), ex=180)


async def _fan_out_resync(days: int) -> int:
    from kanalchi.jobs import telegram_jobs

    async with session_scope() as db:
        rows = (
            await db.execute(
                select(Channel.id)
                .join(Tenant, Tenant.id == Channel.tenant_id)
                .where(Channel.backfill_status == "done", Tenant.status.in_(["active", "indexing"]))
            )
        ).all()
    n = 0
    for (channel_id,) in rows:
        try:
            await telegram_jobs.resync.configure(queueing_lock=f"resync:{channel_id}:{days}").defer_async(
                channel_id=channel_id, days=days
            )
            n += 1
        except Exception as exc:  # noqa: BLE001
            if "already" not in str(exc).lower():
                log.warning("periodic.resync.defer_failed", channel_id=channel_id, error=str(exc))
    log.info("periodic.resync.fan_out", days=days, channels=n)
    return n


@app.periodic(cron="15 */2 * * *")
@app.task(queue="telegram", name="periodic.resync_recent", pass_context=True)
async def resync_recent(context, timestamp: int) -> None:  # noqa: ANN001
    await _fan_out_resync(3)


@app.periodic(cron="30 3 * * *")
@app.task(queue="telegram", name="periodic.resync_month", pass_context=True)
async def resync_month(context, timestamp: int) -> None:  # noqa: ANN001
    await _fan_out_resync(30)


@app.periodic(cron="45 4 * * 0")
@app.task(queue="telegram", name="periodic.resync_quarter", pass_context=True)
async def resync_quarter(context, timestamp: int) -> None:  # noqa: ANN001
    await _fan_out_resync(90)


@app.periodic(cron="*/2 * * * *")
@app.task(queue="index", name="periodic.poll_batches", pass_context=True)
async def poll_batches(context, timestamp: int) -> None:  # noqa: ANN001
    """Check in-flight extraction batches and ingest the ones that ended."""
    from kanalchi.ai.extraction import poll_batches as _poll
    from kanalchi.jobs import index_jobs

    for llm_batch_id in await _poll():
        await index_jobs.ingest_batch.defer_async(llm_batch_id=llm_batch_id)


@app.periodic(cron="20 2 * * *")
@app.task(queue="index", name="periodic.nightly_counts", pass_context=True)
async def nightly_counts(context, timestamp: int) -> None:  # noqa: ANN001
    """Refresh tag post counts and engagement scores after the overnight resyncs."""
    from kanalchi.jobs import index_jobs

    async with session_scope() as db:
        rows = (await db.execute(select(Tenant.id).where(Tenant.status.in_(["active", "indexing"])))).all()
    for (tenant_id,) in rows:
        await index_jobs.recompute_counts.defer_async(tenant_id=tenant_id)
