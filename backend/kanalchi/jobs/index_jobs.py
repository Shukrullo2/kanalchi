"""Jobs executed inside worker-index: embeddings, extraction batches, taxonomy, mapping."""

from __future__ import annotations

from typing import Any

from kanalchi.core.jobs import job_run, update_job_run
from kanalchi.core.logging import get_logger
from kanalchi.jobs.app import app

log = get_logger(__name__)


@app.task(queue="index", name="index.ping")
async def ping(payload: str = "pong") -> str:
    log.info("index.ping", payload=payload)
    return payload


@app.task(queue="index", name="index.post", retry=1)
async def index_post(post_id: int) -> dict[str, Any]:
    """Incremental path for one post: extract, tag, embed."""
    from kanalchi.ai.extraction import extract_one
    from kanalchi.ai.indexing import rebuild_chunks

    result = await extract_one(post_id)
    await rebuild_chunks([post_id])
    return result


@app.task(queue="index", name="index.embed_batch", retry=2)
async def embed_batch(tenant_id: int, post_ids: list[int] | None = None) -> dict[str, Any]:
    from kanalchi.ai.indexing import pending_embed_ids, rebuild_chunks
    from kanalchi.core.settings import get_settings

    size = get_settings().embed_job_posts
    ids = post_ids or await pending_embed_ids(tenant_id, limit=size)
    if not ids:
        return {"chunks": 0}
    chunks = await rebuild_chunks(ids)
    if not post_ids and len(ids) >= size:
        await embed_batch.defer_async(tenant_id=tenant_id)  # keep going in a fresh short job
    return {"chunks": chunks, "posts": len(ids)}


@app.task(queue="index", name="index.backlog", retry=0)
async def index_backlog(tenant_id: int, job_run_id: int | None = None) -> dict[str, Any]:
    """Runs after a backfill completes: profile the channel, embed, then extract in batches."""
    from kanalchi.ai.discovery import discover, ensure_universal_dimensions
    from kanalchi.core.db import session_scope
    from kanalchi.core.models import Tenant

    async with job_run(job_run_id):
        await ensure_universal_dimensions(tenant_id)
        async with session_scope() as db:
            tenant = await db.get(Tenant, tenant_id)
            has_profile = bool((tenant.settings or {}).get("channel_profile"))
            tenant.status = "indexing"
        if not has_profile:
            await update_job_run(job_run_id, progress={"stage": "profiling channel"})
            await discover(tenant_id)
        await update_job_run(job_run_id, progress={"stage": "embedding"})
        await embed_batch.defer_async(tenant_id=tenant_id)
        await update_job_run(job_run_id, progress={"stage": "extracting"})
        await extract_batch.defer_async(tenant_id=tenant_id)
    return {"ok": True}


@app.task(queue="index", name="index.discover", retry=0)
async def discover_dimensions(tenant_id: int, job_run_id: int | None = None) -> dict[str, Any]:
    from kanalchi.ai.discovery import discover

    async with job_run(job_run_id):
        return await discover(tenant_id)


@app.task(queue="index", name="index.extract_batch", retry=1)
async def extract_batch(tenant_id: int, job_run_id: int | None = None) -> dict[str, Any]:
    """Submit one extraction batch; the periodic poller picks up the results."""
    from kanalchi.ai.extraction import submit_batch

    result = await submit_batch(tenant_id)
    await update_job_run(job_run_id, progress={"stage": "batch submitted", **result})
    return result


@app.task(queue="index", name="index.ingest_batch", retry=2)
async def ingest_batch(llm_batch_id: int) -> dict[str, Any]:
    """Ingest a finished batch, embed what it produced, and queue the next batch if work remains."""
    from kanalchi.ai.extraction import ingest_results, pending_extract_ids
    from kanalchi.ai.indexing import rebuild_chunks
    from kanalchi.core.db import session_scope
    from kanalchi.core.models import LlmBatch

    result = await ingest_results(llm_batch_id)
    posts = result.get("posts") or []
    if posts:
        await rebuild_chunks(posts)  # the synthetic Latin chunk needs the extraction to exist first
    async with session_scope() as db:
        row = await db.get(LlmBatch, llm_batch_id)
        tenant_id = row.tenant_id if row else None
    if tenant_id and await pending_extract_ids(tenant_id, limit=1):
        await extract_batch.defer_async(tenant_id=tenant_id)
    elif tenant_id:
        await build_taxonomy.configure(queueing_lock=f"taxonomy:{tenant_id}").defer_async(tenant_id=tenant_id)
    return {k: v for k, v in result.items() if k != "posts"}


@app.task(queue="taxonomy", name="taxonomy.build", retry=0)
async def build_taxonomy(
    tenant_id: int, job_run_id: int | None = None, auto_apply: bool = True
) -> dict[str, Any]:
    """Build a taxonomy version. The first one auto-applies; later rebuilds wait for a human."""
    from kanalchi.ai.taxonomy import apply, build
    from kanalchi.core.db import session_scope
    from kanalchi.core.models import Tenant

    async with job_run(job_run_id):
        async with session_scope() as db:
            tenant = await db.get(Tenant, tenant_id)
            first_build = tenant.active_taxonomy_version_id is None
        result = await build(tenant_id, job_run_id=job_run_id)
        if auto_apply and first_build:
            await update_job_run(job_run_id, progress={"stage": "applying"})
            result |= await apply(tenant_id, result["version_id"], job_run_id=job_run_id)
        async with session_scope() as db:
            tenant = await db.get(Tenant, tenant_id)
            if tenant.status == "indexing":
                tenant.status = "active"
        return result


@app.task(queue="taxonomy", name="taxonomy.apply", retry=0)
async def apply_taxonomy(tenant_id: int, version_id: int, job_run_id: int | None = None) -> dict[str, Any]:
    from kanalchi.ai.taxonomy import apply

    async with job_run(job_run_id):
        return await apply(tenant_id, version_id, job_run_id=job_run_id)


@app.task(queue="taxonomy", name="taxonomy.reassign", retry=0)
async def reassign(tenant_id: int, job_run_id: int | None = None) -> dict[str, Any]:
    from kanalchi.ai.taxonomy import embed_tags, reassign_all, recompute_counts

    async with job_run(job_run_id):
        await embed_tags(tenant_id)
        n = await reassign_all(tenant_id, job_run_id=job_run_id)
        await recompute_counts(tenant_id)
        return {"reassigned": n}


@app.task(queue="index", name="index.recompute_counts", retry=1)
async def recompute_counts(tenant_id: int) -> dict[str, Any]:
    from kanalchi.ai.taxonomy import recompute_counts as _recompute

    await _recompute(tenant_id)
    return {"ok": True}


@app.task(queue="taxonomy", name="index.build_threads", retry=0)
async def build_threads(tenant_id: int, job_run_id: int | None = None) -> dict[str, Any]:
    from kanalchi.ai.threads import build_threads as _build

    async with job_run(job_run_id):
        return await _build(tenant_id, job_run_id=job_run_id)


@app.task(queue="index", name="index.entity_summary", retry=1)
async def entity_summary(tenant_id: int, tag_id: int) -> dict[str, Any]:
    from kanalchi.ai.threads import build_entity_summary

    return await build_entity_summary(tenant_id, tag_id)


@app.task(queue="index", name="index.refresh_summaries", retry=0)
async def refresh_summaries(tenant_id: int, limit: int = 10) -> dict[str, Any]:
    """Regenerate the summaries that new posts have made stale, a few at a time."""
    from kanalchi.ai.threads import mark_summaries_stale, stale_summary_tag_ids

    await mark_summaries_stale(tenant_id)
    tag_ids = await stale_summary_tag_ids(tenant_id, limit=limit)
    for tag_id in tag_ids:
        await entity_summary.defer_async(tenant_id=tenant_id, tag_id=tag_id)
    return {"queued": len(tag_ids)}
