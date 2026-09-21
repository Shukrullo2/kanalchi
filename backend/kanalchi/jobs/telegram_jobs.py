"""Jobs executed inside worker-telegram (the only process that owns Telethon clients)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from kanalchi.core.crypto import decrypt
from kanalchi.core.db import session_scope
from kanalchi.core.jobs import job_run, update_job_run
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, JobRun, Post
from kanalchi.core.redis import get_redis
from kanalchi.jobs.app import app

log = get_logger(__name__)


@app.task(queue="telegram", name="telegram.ping")
async def ping(payload: str = "pong") -> str:
    log.info("telegram.ping", payload=payload)
    return payload


# ------------------------------------------------------------------ account login handshake
@app.task(queue="telegram", name="telegram.account_login_start", retry=0)
async def account_login_start(account_id: int) -> None:
    from kanalchi.telegram.pool import get_pool

    await get_pool().login_start(account_id)


async def _pop_secret(key: str) -> str | None:
    r = get_redis()
    val = await r.get(key)
    if val:
        await r.delete(key)
        return decrypt(val)
    return None


@app.task(queue="telegram", name="telegram.account_login_code", retry=0)
async def account_login_code(account_id: int) -> None:
    from kanalchi.telegram.pool import get_pool

    code = await _pop_secret(f"tglogin:{account_id}:code")
    if code:
        await get_pool().login_code(account_id, code)


@app.task(queue="telegram", name="telegram.account_login_password", retry=0)
async def account_login_password(account_id: int) -> None:
    from kanalchi.telegram.pool import get_pool

    password = await _pop_secret(f"tglogin:{account_id}:password")
    if password:
        await get_pool().login_password(account_id, password)


# ------------------------------------------------------------------ onboarding / history
@app.task(queue="telegram", name="telegram.channel_resolve", retry=0)
async def channel_resolve(
    tenant_id: int,
    link: str,
    account_id: int,
    allow_join_private: bool = False,
    job_run_id: int | None = None,
) -> dict:
    from kanalchi.telegram.onboarding import resolve_channel

    async with job_run(job_run_id):
        out = await resolve_channel(tenant_id, link, account_id, allow_join_private)
        await update_job_run(
            job_run_id, progress={"message": f"resolved {out['title']}", "total": out["total"]}
        )
        return out


@app.task(queue="telegram", name="telegram.backfill_chunk", retry=2)
async def backfill_chunk(channel_id: int) -> dict:
    from kanalchi.telegram.ingest import backfill_chunk as _chunk

    out = await _chunk(channel_id)
    # keep the admin-facing backfill job record in sync
    async with session_scope() as db:
        ch = await db.get(Channel, channel_id)
        jr = await db.scalar(
            select(JobRun)
            .where(JobRun.type == "backfill", JobRun.params["channel_id"].as_integer() == channel_id)
            .order_by(JobRun.id.desc())
        )
        if ch is not None and jr is not None and jr.status in {"queued", "running"}:
            done = await db.scalar(
                select(func.count()).select_from(Post).where(Post.channel_id == channel_id)
            )
            jr.status = (
                "running" if out.get("more") else ("succeeded" if ch.backfill_status == "done" else "running")
            )
            jr.started_at = jr.started_at or datetime.now(UTC)
            jr.progress = {
                **(jr.progress or {}),
                "done": done,
                "total": ch.backfill_total_estimate,
                "checkpoint": ch.backfill_checkpoint,
                "stage": "history",
            }
            if jr.status == "succeeded":
                jr.finished_at = datetime.now(UTC)
    return out


@app.task(queue="telegram", name="telegram.resync", retry=1)
async def resync(channel_id: int, days: int = 3) -> dict:
    from kanalchi.telegram.ingest import resync as _resync

    return await _resync(channel_id, days)


# ------------------------------------------------------------------ media
@app.task(queue="media", name="media.fetch", retry=0)
async def fetch_media(media_id: int) -> dict:
    from kanalchi.telegram.media import fetch_media as _fetch

    return await _fetch(media_id)
