"""Periodic tasks. procrastinate dedupes periodic runs across workers via the `timestamp` argument."""

from __future__ import annotations

from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import or_, select

from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, Tenant, UsageLedger
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
                .where(
                    Channel.backfill_status == "done",
                    Tenant.status.in_(["active", "indexing"]),
                    # The archive plan is a snapshot: nothing new is read after the import.
                    or_(Tenant.plan.is_(None), Tenant.plan != "archive"),
                )
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


@app.periodic(cron="*/10 * * * *")
@app.task(queue="index", name="periodic.pipeline_reconcile", pass_context=True)
async def pipeline_reconcile(context, timestamp: int) -> None:  # noqa: ANN001
    """Re-queue whatever step a channel is missing, so a lost job never strands an import."""
    from kanalchi.jobs.pipeline import reconcile_all

    await reconcile_all()


@app.periodic(cron="*/2 * * * *")
@app.task(queue="index", name="periodic.poll_batches", pass_context=True)
async def poll_batches(context, timestamp: int) -> None:  # noqa: ANN001
    """Check in-flight extraction batches and ingest the ones that ended."""
    from kanalchi.ai.extraction import poll_batches as _poll
    from kanalchi.jobs import index_jobs

    for llm_batch_id in await _poll():
        try:
            await index_jobs.ingest_batch.configure(queueing_lock=f"ingest:{llm_batch_id}").defer_async(
                llm_batch_id=llm_batch_id
            )
        except AlreadyEnqueued:
            pass  # the reconciler got there first; one ingest per batch is the point


@app.periodic(cron="20 2 * * *")
@app.task(queue="index", name="periodic.nightly_counts", pass_context=True)
async def nightly_counts(context, timestamp: int) -> None:  # noqa: ANN001
    """Refresh tag post counts and engagement scores after the overnight resyncs."""
    from kanalchi.jobs import index_jobs

    async with session_scope() as db:
        rows = (await db.execute(select(Tenant.id).where(Tenant.status.in_(["active", "indexing"])))).all()
    for (tenant_id,) in rows:
        await index_jobs.recompute_counts.defer_async(tenant_id=tenant_id)


@app.periodic(cron="40 3 * * *")
@app.task(queue="index", name="periodic.refresh_summaries", pass_context=True)
async def refresh_summaries(context, timestamp: int) -> None:  # noqa: ANN001
    """Entity summaries go stale as soon as the tag picks up a newer post."""
    from kanalchi.jobs import index_jobs

    async with session_scope() as db:
        rows = (await db.execute(select(Tenant.id).where(Tenant.status == "active"))).all()
    for (tenant_id,) in rows:
        await index_jobs.refresh_summaries.defer_async(tenant_id=tenant_id)


@app.periodic(cron="0 4 * * 1")
@app.task(queue="taxonomy", name="periodic.weekly_threads", pass_context=True)
async def weekly_threads(context, timestamp: int) -> None:  # noqa: ANN001
    from kanalchi.jobs import index_jobs

    async with session_scope() as db:
        rows = (await db.execute(select(Tenant.id).where(Tenant.status == "active"))).all()
    for (tenant_id,) in rows:
        try:
            await index_jobs.build_threads.configure(queueing_lock=f"threads:{tenant_id}").defer_async(
                tenant_id=tenant_id
            )
        except Exception as exc:  # noqa: BLE001
            if "already" not in str(exc).lower():
                log.warning("periodic.threads.defer_failed", tenant_id=tenant_id, error=str(exc))


@app.periodic(cron="30 5 * * 1")
@app.task(queue="index", name="periodic.pending_digest", pass_context=True)
async def pending_digest(context, timestamp: int) -> None:  # noqa: ANN001
    """Weekly nudge to the platform admins: how many names per channel are waiting to become tags.
    The index is curated in the console, so this is theirs to act on, not the bloggers'."""
    from sqlalchemy import func

    from kanalchi.core.models import TagCandidate
    from kanalchi.core.settings import get_settings

    async with session_scope() as db:
        rows = (
            await db.execute(
                select(Tenant.id, Tenant.domain, func.count(TagCandidate.id))
                .join(TagCandidate, TagCandidate.tenant_id == Tenant.id)
                .where(
                    Tenant.status == "active",
                    TagCandidate.status == "pending",
                    TagCandidate.count >= 3,
                )
                .group_by(Tenant.id, Tenant.domain)
                .order_by(func.count(TagCandidate.id).desc())
            )
        ).all()
    if not rows:
        return
    settings = get_settings()
    lines = [
        f"{domain}: {count} names waiting — {settings.public_url(settings.admin_host, f'/tenants/{tenant_id}/index')}"
        for tenant_id, domain, count in rows[:20]
    ]
    await _alert_admins("Index review this week:\n" + "\n".join(lines))


async def _alert_admins(message: str) -> None:
    """Platform-level alerts go to the allow-listed admins through the platform bot."""
    from aiogram import Bot

    from kanalchi.core.models import PlatformAdmin
    from kanalchi.core.settings import get_settings

    settings = get_settings()
    if not settings.platform_bot_token:
        log.warning("alert.no_platform_bot", message=message)
        return
    async with session_scope() as db:
        rows = (await db.execute(select(PlatformAdmin.tg_user_id))).all()
    recipients = {r[0] for r in rows} | set(settings.admin_tg_ids)
    if not recipients:
        return
    async with Bot(settings.platform_bot_token) as bot:
        for tg_user_id in recipients:
            try:
                await bot.send_message(tg_user_id, message)
            except Exception as exc:  # noqa: BLE001
                log.info("alert.send_failed", tg_user_id=tg_user_id, error=str(exc)[:200])


@app.periodic(cron="*/15 * * * *")
@app.task(queue="index", name="periodic.health_alerts", pass_context=True)
async def health_alerts(context, timestamp: int) -> None:  # noqa: ANN001
    """Things an operator needs to hear about within minutes, not at the next login.

    Each alert is sent at most once an hour, so a persistent problem does not become a flood.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func

    from kanalchi.core.models import LlmBatch, TelegramAccount
    from kanalchi.core.redis import get_redis
    from kanalchi.core.settings import get_settings

    redis = get_redis()

    async def once_per_hour(key: str, message: str) -> None:
        try:
            if await redis.set(f"alert:{key}", "1", ex=3600, nx=True):
                await _alert_admins(message)
        except Exception as exc:  # noqa: BLE001
            log.warning("alert.dedupe_failed", key=key, error=str(exc)[:200])

    async with session_scope() as db:
        dead = (
            await db.execute(
                select(TelegramAccount.id, TelegramAccount.phone).where(TelegramAccount.status == "dead")
            )
        ).all()
        stuck = (
            await db.execute(
                select(LlmBatch.id, LlmBatch.anthropic_batch_id).where(
                    LlmBatch.status.in_(["submitted", "in_progress"]),
                    LlmBatch.submitted_at < datetime.now(UTC) - timedelta(hours=24),
                )
            )
        ).all()
        spend_today = await db.scalar(
            select(func.coalesce(func.sum(UsageLedger.cost_usd), 0)).where(
                UsageLedger.day == func.current_date()
            )
        )

    for account_id, phone in dead:
        await once_per_hour(
            f"account:{account_id}",
            f"⚠️ Telegram account {phone} is signed out. Ingestion has stopped for its channels.",
        )

    for batch_id, anthropic_id in stuck:
        await once_per_hour(
            f"batch:{batch_id}", f"⚠️ Extraction batch {anthropic_id} has been running for over 24 hours."
        )

    settings = get_settings()
    cap = settings.platform_daily_llm_cap_usd
    if cap and float(spend_today or 0) >= cap * 0.8:
        await once_per_hour(
            "platform-budget",
            f"⚠️ Platform assistant spend today is ${float(spend_today):.2f} of a ${cap:.0f} cap.",
        )

    # The telegram worker owns every MTProto session, so a missing heartbeat means ingestion is down.
    try:
        if not await redis.exists("hb:worker-telegram"):
            await once_per_hour(
                "worker-telegram", "⚠️ worker-telegram has not reported in. Telegram ingestion is down."
            )
    except Exception:  # noqa: BLE001
        pass
