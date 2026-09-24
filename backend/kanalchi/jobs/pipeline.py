"""The indexing pipeline as one reconciler.

Three questions the console keeps asking about a channel — where is it, what will it cost,
what should run next — answered from the database rather than from whichever job happened
to be running. `reconcile` only ever queues work that is missing: every step it queues is
idempotent and takes a queueing lock, so it is safe on a timer, on a button, and after a
crash, and the pipeline heals instead of sitting on a lost job.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import func, select

from kanalchi.core.db import session_scope
from kanalchi.core.jobs import create_job_run, delete_job_run
from kanalchi.core.logging import get_logger
from kanalchi.core.models import (
    Channel,
    Extraction,
    JobRun,
    LlmBatch,
    Post,
    TaxonomyVersion,
    Tenant,
)
from kanalchi.core.pricing import Usage, cost_usd, embed_cost_usd
from kanalchi.core.redis import get_redis
from kanalchi.core.settings import get_settings

log = get_logger(__name__)

STALE_BATCH = timedelta(hours=24)
# A step that just failed is not queued again straight away; the failure stays visible
# in the console for this long before the reconciler tries once more.
RETRY_AFTER_FAILURE = timedelta(minutes=20)
MIN_POSTS_TO_PROFILE = 5

# Measured on the first real channel (12.3k posts, 2026-09-22) for the steps that are not
# priced per token here. They make the quote read "about $8", which is what it is for.
DISCOVERY_USD = 0.70
TAXONOMY_USD_PER_POST = 0.00045
SUMMARIES_USD_PER_POST = 0.0002
SYSTEM_PROMPT_TOKENS = 2500  # the cached prefix of every extraction request
PER_POST_OVERHEAD_TOKENS = 200  # the user-turn framing around the post text
CHARS_PER_TOKEN = 3.2  # Cyrillic and Latin Uzbek both tokenise densely
DEFAULT_POST_TOKENS = 280
DEFAULT_OUTPUT_TOKENS = 1100  # extraction JSON plus adaptive thinking, measured
DEFAULT_TEXT_SHARE = 0.9  # posts with any text, for a channel not yet imported

STAGES = ("import", "profile", "embed", "extract", "taxonomy")


def _posts_q(tenant_id: int):
    return (
        select(func.count())
        .select_from(Post)
        .where(Post.tenant_id == tenant_id, Post.is_deleted.is_(False), Post.is_album_root.is_(True))
    )


async def _worker_alive(name: str) -> bool | None:
    try:
        return bool(await get_redis().exists(f"hb:{name}"))
    except Exception:  # noqa: BLE001
        return None


async def pipeline_status(tenant_id: int) -> dict[str, Any]:
    """Everything the monitor shows: per-stage counts, what is in flight, and what needs a human."""
    s = get_settings()
    now = datetime.now(UTC)
    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        if tenant is None:
            return {}
        channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
        posts = await db.scalar(_posts_q(tenant_id)) or 0
        text_posts = await db.scalar(_posts_q(tenant_id).where(func.length(Post.text) > 0)) or 0
        by_index = dict(
            (
                await db.execute(
                    select(Post.index_status, func.count())
                    .where(
                        Post.tenant_id == tenant_id,
                        Post.is_deleted.is_(False),
                        Post.is_album_root.is_(True),
                    )
                    .group_by(Post.index_status)
                )
            ).all()
        )
        by_ext = dict(
            (
                await db.execute(
                    select(Extraction.status, func.count())
                    .where(Extraction.tenant_id == tenant_id)
                    .group_by(Extraction.status)
                )
            ).all()
        )
        open_batches = (
            await db.scalars(
                select(LlmBatch)
                .where(LlmBatch.tenant_id == tenant_id, LlmBatch.ingested_at.is_(None))
                .order_by(LlmBatch.id.desc())
                .limit(5)
            )
        ).all()
        latest_version = await db.scalar(
            select(TaxonomyVersion)
            .where(TaxonomyVersion.tenant_id == tenant_id)
            .order_by(TaxonomyVersion.id.desc())
            .limit(1)
        )
        failures = (
            await db.execute(
                select(JobRun.type, JobRun.error, JobRun.finished_at)
                .where(
                    JobRun.tenant_id == tenant_id,
                    JobRun.status == "failed",
                    JobRun.finished_at > now - timedelta(hours=6),
                )
                .order_by(JobRun.id.desc())
                .limit(5)
            )
        ).all()
        running = (
            await db.execute(
                select(JobRun.type, JobRun.progress)
                .where(JobRun.tenant_id == tenant_id, JobRun.status == "running")
                .order_by(JobRun.id.desc())
                .limit(5)
            )
        ).all()
        # A run still "queued" an hour on was never picked up: the worker is down, or is
        # running code too old to accept the job. Either way a person has to act.
        unclaimed = await db.scalar(
            select(func.count())
            .select_from(JobRun)
            .where(
                JobRun.tenant_id == tenant_id,
                JobRun.status == "queued",
                JobRun.created_at < now - timedelta(hours=1),
            )
        )
        imported = (
            await db.scalar(select(func.count()).select_from(Post).where(Post.channel_id == channel.id))
            if channel
            else 0
        )
        profile = bool((tenant.settings or {}).get("channel_profile"))
        active_version = tenant.active_taxonomy_version_id
        tenant_status = tenant.status

    succeeded = by_ext.get("succeeded", 0)
    in_flight = by_ext.get("submitted", 0) + by_ext.get("queued", 0)
    failed = by_ext.get("errored", 0) + by_ext.get("refused", 0) + by_ext.get("invalid", 0)
    # Statuses only ever advance past "pending" (embedded, extracted, tagged…); anything
    # that is neither pending nor too short has its vectors.
    skipped = by_index.get("skipped", 0)
    pending_embed = by_index.get("pending", 0)
    embedded = max(0, posts - pending_embed - skipped)
    pending_extract = max(0, text_posts - succeeded - in_flight - failed)

    stages = {
        "import": {
            "done": channel is not None and channel.backfill_status == "done",
            "status": channel.backfill_status if channel else None,
            "imported": imported or 0,
            "total": channel.backfill_total_estimate if channel else None,
        },
        "profile": {"done": profile, "possible": text_posts >= MIN_POSTS_TO_PROFILE},
        "embed": {
            "done": posts > 0 and pending_embed == 0,
            "embedded": embedded,
            "skipped": skipped,
            "pending": pending_embed,
            "total": posts,
        },
        "extract": {
            "done": text_posts > 0 and pending_extract == 0 and in_flight == 0,
            "succeeded": succeeded,
            "in_flight": in_flight,
            "failed": failed,
            "pending": pending_extract,
            "total": text_posts,
            "batches": [
                {
                    "id": b.id,
                    "status": b.status,
                    "requests": b.request_count,
                    "submitted_at": b.submitted_at,
                    "stale": bool(b.submitted_at and now - b.submitted_at > STALE_BATCH),
                }
                for b in open_batches
            ],
        },
        "taxonomy": {
            "done": active_version is not None,
            "version_no": latest_version.version_no if latest_version else None,
            "status": latest_version.status if latest_version else None,
            "version_id": latest_version.id if latest_version else None,
        },
    }
    stage = next((name for name in STAGES if not stages[name]["done"]), "done")

    attention: list[str] = []
    if tenant_status == "paused":
        attention.append("The channel is paused: nothing is queued until it is resumed.")
    if not s.anthropic_api_key:
        attention.append(
            "ANTHROPIC_API_KEY is not configured, so profiling, extraction and the taxonomy cannot run."
        )
    if not s.voyage_api_key:
        attention.append("VOYAGE_API_KEY is not configured, so embeddings (and semantic search) cannot run.")
    workers = {
        "telegram": await _worker_alive("worker-telegram"),
        "index": await _worker_alive("worker-index"),
    }
    if workers["telegram"] is False and stage == "import":
        attention.append("worker-telegram is not running; the import cannot proceed.")
    if workers["index"] is False and stage in {"profile", "embed", "extract", "taxonomy"}:
        attention.append("worker-index is not running; nothing past the import can proceed.")
    for b in stages["extract"]["batches"]:
        if b["stale"]:
            attention.append(f"Extraction batch #{b['id']} has been open for more than 24 hours.")
    for kind, error, _ in failures:
        attention.append(f"{kind} failed: {(error or 'no details')[:160]}")
    if unclaimed:
        attention.append(
            f"{unclaimed} queued job{'s' if unclaimed > 1 else ''} never started in over an hour: "
            "check that the workers are running the current code (restart them after a deploy)."
        )

    return {
        "stage": stage,
        "tenant_status": tenant_status,
        "stages": stages,
        "running": [{"type": t, "progress": p or {}} for t, p in running],
        "attention": attention,
        "workers": workers,
        "checked_at": now,
    }


def estimate_lines(
    total: int,
    *,
    avg_tokens: float = DEFAULT_POST_TOKENS,
    text_share: float = DEFAULT_TEXT_SHARE,
    extracted: int = 0,
    embedded: int = 0,
    profile: bool = False,
    has_taxonomy: bool = False,
) -> dict[str, float]:
    """The cost of each remaining step for an archive of `total` posts, in dollars.

    Pure, so the sign-up quote can price a channel that has nothing imported yet.
    """
    s = get_settings()
    expected_text_posts = int(total * text_share)
    to_extract = max(0, expected_text_posts - extracted)
    per_post = cost_usd(
        s.extract_model,
        Usage(
            input_tokens=int(avg_tokens) + PER_POST_OVERHEAD_TOKENS,
            cache_read_tokens=SYSTEM_PROMPT_TOKENS,
            output_tokens=DEFAULT_OUTPUT_TOKENS,
        ),
        batch=True,
    )
    to_embed = max(0, total - embedded)
    # The original text and the synthetic Latin summary, in chunks: measured at about four
    # times the post's own tokens on the first real channel (2026-09-25).
    embedding = embed_cost_usd(s.embed_model, int(to_embed * avg_tokens * 4))
    return {
        "extraction": round(per_post * to_extract, 2),
        "embedding": round(embedding, 2),
        "profile": 0.0 if profile else round(DISCOVERY_USD, 2),
        "taxonomy": 0.0 if has_taxonomy else round(TAXONOMY_USD_PER_POST * total, 2),
        "summaries": round(SUMMARIES_USD_PER_POST * total, 2),
    }


async def estimate(tenant_id: int) -> dict[str, Any]:
    """What finishing this channel will cost, from what is known before and after the import.

    Before the import only the message count is known, so the text length is a default; once
    posts exist the channel's own average is used and the steps already done are left out.
    """
    s = get_settings()
    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
        posts = await db.scalar(_posts_q(tenant_id)) or 0
        text_posts = await db.scalar(_posts_q(tenant_id).where(func.length(Post.text) > 0)) or 0
        avg_chars = await db.scalar(
            select(func.avg(func.length(Post.text))).where(
                Post.tenant_id == tenant_id, Post.is_deleted.is_(False), func.length(Post.text) > 0
            )
        )
        extracted = await db.scalar(
            select(func.count())
            .select_from(Extraction)
            .where(Extraction.tenant_id == tenant_id, Extraction.status == "succeeded")
        )
        embedded = await db.scalar(
            _posts_q(tenant_id).where(Post.index_status.in_(["embedded", "extracted", "skipped"]))
        )
        profile = bool(tenant and (tenant.settings or {}).get("channel_profile"))
        has_taxonomy = bool(tenant and tenant.active_taxonomy_version_id)

    total = max(posts, (channel.backfill_total_estimate if channel else 0) or 0)
    text_share = (text_posts / posts) if posts else DEFAULT_TEXT_SHARE
    avg_tokens = (float(avg_chars) / CHARS_PER_TOKEN) if avg_chars else DEFAULT_POST_TOKENS
    to_extract = max(0, int(total * text_share) - (extracted or 0))
    lines = estimate_lines(
        total,
        avg_tokens=avg_tokens,
        text_share=text_share,
        extracted=extracted or 0,
        embedded=embedded or 0,
        profile=profile,
        has_taxonomy=has_taxonomy,
    )
    out: dict[str, Any] = {
        "posts_total": total,
        "posts_imported": posts,
        "avg_post_tokens": int(avg_tokens),
        "measured_from_channel": bool(avg_chars),
        "lines": lines,
        "total_usd": round(sum(lines.values()), 2),
        "models": {"extract": s.extract_model, "embed": s.embed_model, "taxonomy": s.taxonomy_model},
    }
    # With a key and real posts the extraction line can be token-counted instead of guessed.
    if s.anthropic_api_key and to_extract:
        try:
            from kanalchi.ai.extraction import estimate_cost

            measured = await estimate_cost(tenant_id)
            if measured.get("posts_pending"):
                out["extraction_measured_usd"] = measured["estimated_usd"]
        except Exception as exc:  # noqa: BLE001
            out["extraction_measured_error"] = type(exc).__name__
    return out


async def _recently_failed(tenant_id: int, kind: str) -> bool:
    async with session_scope() as db:
        at = await db.scalar(
            select(func.max(JobRun.finished_at)).where(
                JobRun.tenant_id == tenant_id, JobRun.type == kind, JobRun.status == "failed"
            )
        )
    return bool(at and datetime.now(UTC) - at < RETRY_AFTER_FAILURE)


async def reconcile(tenant_id: int, *, force: bool = False) -> list[str]:
    """Queue whatever the pipeline is missing for this tenant and say what was done.

    `force` skips the back-off after a failure — the button in the console — and never
    skips a missing key or a paused channel, because those would only fail again.
    """
    from kanalchi.ai.extraction import pending_extract_ids
    from kanalchi.ai.indexing import pending_embed_ids
    from kanalchi.jobs import index_jobs, telegram_jobs

    s = get_settings()
    actions: list[str] = []

    async def queue(label: str, task, *, lock: str, kind: str | None = None, **kwargs: Any) -> None:  # noqa: ANN001
        if kind and not force and await _recently_failed(tenant_id, kind):
            actions.append(f"{label}: failed recently, waiting before retrying")
            return
        if kind:
            kwargs["job_run_id"] = await create_job_run(tenant_id, kind, {"trigger": "reconcile"})
        try:
            await task.configure(queueing_lock=lock).defer_async(**kwargs)
            actions.append(f"{label}: queued")
        except AlreadyEnqueued:
            await delete_job_run(kwargs.get("job_run_id"))
            actions.append(f"{label}: already queued")
        except Exception:
            await delete_job_run(kwargs.get("job_run_id"))
            raise

    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        if tenant is None:
            return ["tenant not found"]
        if tenant.status in {"paused", "archived", "onboarding"}:
            return [f"channel is {tenant.status}; nothing queued"]
        channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
        text_posts = await db.scalar(_posts_q(tenant_id).where(func.length(Post.text) > 0)) or 0
        succeeded = await db.scalar(
            select(func.count())
            .select_from(Extraction)
            .where(Extraction.tenant_id == tenant_id, Extraction.status == "succeeded")
        )
        in_flight = await db.scalar(
            select(func.count())
            .select_from(LlmBatch)
            .where(LlmBatch.tenant_id == tenant_id, LlmBatch.status.in_(["submitted", "in_progress"]))
        )
        ended = (
            await db.scalars(
                select(LlmBatch.id).where(
                    LlmBatch.tenant_id == tenant_id,
                    LlmBatch.status == "ended",
                    LlmBatch.ingested_at.is_(None),
                )
            )
        ).all()
        latest_version = await db.scalar(
            select(TaxonomyVersion.status)
            .where(TaxonomyVersion.tenant_id == tenant_id)
            .order_by(TaxonomyVersion.id.desc())
            .limit(1)
        )
        profile = bool((tenant.settings or {}).get("channel_profile"))
        active_version = tenant.active_taxonomy_version_id
        tenant_status = tenant.status

    if channel is None:
        return ["no channel attached yet"]
    if channel.telegram_account_id is None:
        return ["the channel has no Telegram account"]

    # 1. History. Everything else waits for it.
    if channel.backfill_status != "done":
        await queue(
            "import", telegram_jobs.backfill_chunk, lock=f"backfill:{channel.id}", channel_id=channel.id
        )
        return actions

    # 2. Channel profile — improves extraction, but nothing below is blocked on it.
    if not profile and text_posts >= MIN_POSTS_TO_PROFILE and s.anthropic_api_key:
        await queue(
            "profile",
            index_jobs.discover_dimensions,
            lock=f"discover:{tenant_id}",
            kind="discover",
            tenant_id=tenant_id,
        )

    # 3. Embeddings.
    if s.voyage_api_key and await pending_embed_ids(tenant_id, limit=1):
        await queue(
            "embed", index_jobs.embed_batch, lock=f"embed:{tenant_id}", kind="embed", tenant_id=tenant_id
        )

    # 4. Extraction: finished batches first, then the next one, then the taxonomy.
    if s.anthropic_api_key:
        for batch_id in ended:
            await queue(
                f"ingest batch #{batch_id}",
                index_jobs.ingest_batch,
                lock=f"ingest:{batch_id}",
                llm_batch_id=batch_id,
            )
        if not ended and not in_flight:
            if await pending_extract_ids(tenant_id, limit=1):
                await queue(
                    "extract",
                    index_jobs.extract_batch,
                    lock=f"extract:{tenant_id}",
                    kind="extract",
                    tenant_id=tenant_id,
                )
            elif succeeded and active_version is None and latest_version not in {"building", "proposed"}:
                await queue(
                    "taxonomy",
                    index_jobs.build_taxonomy,
                    lock=f"taxonomy:{tenant_id}",
                    kind="taxonomy",
                    tenant_id=tenant_id,
                )
            elif latest_version == "proposed" and active_version is None:
                actions.append("taxonomy: a proposal is waiting to be applied")

    # 5. A channel that has everything is active, whatever job last touched its status.
    if tenant_status in {"backfilling", "indexing"} and active_version is not None and not in_flight:
        if not await pending_extract_ids(tenant_id, limit=1):
            async with session_scope() as db:
                t = await db.get(Tenant, tenant_id)
                if t and t.status in {"backfilling", "indexing"}:
                    t.status = "active"
            actions.append("status: active")

    if not actions:
        actions.append("nothing to do")
    log.info("pipeline.reconcile", tenant_id=tenant_id, actions=actions)
    return actions


async def reconcile_all() -> dict[int, list[str]]:
    async with session_scope() as db:
        ids = (
            await db.scalars(
                select(Tenant.id).where(Tenant.status.in_(["backfilling", "indexing", "active"]))
            )
        ).all()
    out: dict[int, list[str]] = {}
    for tenant_id in ids:
        try:
            out[tenant_id] = await reconcile(tenant_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("pipeline.reconcile_failed", tenant_id=tenant_id, error=str(exc)[:200])
            out[tenant_id] = [f"reconcile failed: {type(exc).__name__}"]
    return out
