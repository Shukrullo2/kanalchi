"""Per-post extraction with Claude Sonnet 5 through the Message Batches API.

Bulk work goes through batches: half price, and a single submission covers thousands of posts.
The batch is created inside the same transaction that records `llm_batches` + `extractions`, so a
crash can never lose track of a submitted batch. Results arrive unordered and are keyed by `custom_id`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from sqlalchemy import Float, cast, func, select, update
from sqlalchemy.dialects.postgresql import insert

from kanalchi.ai import prompts
from kanalchi.ai.claude import get_client, json_format, record_usage, system_blocks
from kanalchi.ai.schemas import EXTRACT_PROMPT_VERSION, EXTRACTOR_VERSION, PostExtraction, schema_of
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, Dimension, Extraction, LlmBatch, Post, PostLink, Tag, Tenant
from kanalchi.core.pricing import Usage, cost_usd
from kanalchi.core.settings import get_settings

log = get_logger(__name__)

BATCH_SIZE = 5000
# What a post costs to write out when nothing has been measured yet: this
# schema plus adaptive thinking runs near 1,100 tokens on real Uzbek posts.
DEFAULT_OUTPUT_TOKENS = 1100
MAX_IN_FLIGHT = 3
MAX_ATTEMPTS = 3
MAX_TOKENS = 6000
POST_CHARS = 6000


def custom_id(post_id: int) -> str:
    """The Batches API only accepts `[a-zA-Z0-9_-]{1,64}` here, so no colons."""
    return f"x-{EXTRACTOR_VERSION}-{post_id}"


def parse_custom_id(cid: str) -> int | None:
    try:
        return int(cid.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None


async def _taxonomy_digest(db, tenant_id: int) -> str:
    """Active canonical tags injected into the prompt so incremental extraction maps directly."""
    rows = (
        await db.execute(
            select(Dimension.key, Tag.canonical_name, Tag.slug)
            .join(Tag, Tag.dimension_id == Dimension.id)
            .where(Tag.tenant_id == tenant_id, Tag.status == "active")
            .order_by(Dimension.sort_order, Tag.post_count.desc())
        )
    ).all()
    if not rows:
        return ""
    by_dim: dict[str, list[dict[str, str]]] = {}
    for key, name, slug in rows:
        bucket = by_dim.setdefault(key, [])
        if len(bucket) < 300:
            bucket.append({"canonical_name": name, "slug": slug})
    sections = [prompts.taxonomy_section(k, v) for k, v in by_dim.items()]
    return (
        "Existing taxonomy. Put the slugs of tags this post belongs to in `taxonomy_mapped`, and put "
        "anything genuinely new in `new_candidates`:\n" + "\n".join(s for s in sections if s)
    )


async def build_prompt(tenant_id: int) -> tuple[list[dict[str, Any]], str]:
    """(system blocks, channel title). The blocks are byte-stable so the batch can hit the prompt cache."""
    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
        custom_dims = (
            await db.execute(
                select(Dimension.key, Dimension.extraction_hint, Dimension.description)
                .where(
                    Dimension.tenant_id == tenant_id,
                    Dimension.is_universal.is_(False),
                    Dimension.is_visible.is_(True),
                )
                .order_by(Dimension.sort_order)
            )
        ).all()
        digest = await _taxonomy_digest(db, tenant_id)

    profile = (tenant.settings or {}).get("channel_profile")
    dims = [{"key": k, "extraction_hint": h, "description": d} for k, h, d in custom_dims]
    stable = prompts.extraction_system(profile, dims)
    blocks = system_blocks(stable, digest) if digest else system_blocks(stable)
    return blocks, (channel.title if channel else (tenant.title or ""))


# Haiku 4.5 rejects both `output_config.effort` and adaptive thinking, so a request
# aimed at it has to be shaped differently. Everything else — system prompt, user
# content, schema — stays identical, which is what makes a model comparison fair.
HAIKU_PREFIX = "claude-haiku"


def _request(post: dict[str, Any], system: list[dict[str, Any]], model: str) -> Request:
    output_config: dict[str, Any] = {"format": json_format(schema_of(PostExtraction))}
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": prompts.extraction_user(post)}],
        "output_config": output_config,
    }
    if model.startswith(HAIKU_PREFIX):
        # No thinking: Haiku 4.5 takes budget_tokens rather than adaptive, and this
        # is a fill-in-the-schema task rather than a reasoning one.
        params["thinking"] = {"type": "disabled"}
    else:
        output_config["effort"] = "low"
        params["thinking"] = {"type": "adaptive"}
    return Request(custom_id=custom_id(post["id"]), params=MessageCreateParamsNonStreaming(**params))


async def _posts_payload(db, post_ids: list[int], channel_title: str) -> list[dict[str, Any]]:
    rows = (await db.scalars(select(Post).where(Post.id.in_(post_ids)))).all()
    links = (
        await db.execute(select(PostLink.post_id, PostLink.url).where(PostLink.post_id.in_(post_ids)))
    ).all()
    by_post: dict[int, list[str]] = {}
    for pid, url in links:
        by_post.setdefault(pid, []).append(url)
    out = []
    for p in rows:
        out.append(
            {
                "id": p.id,
                "text": (p.text or "")[:POST_CHARS],
                "date": p.date.date().isoformat(),
                "media_kind": p.media_kind,
                "channel_title": channel_title,
                "links": by_post.get(p.id, []),
                "forward_from": (p.forward_from or {}).get("title") if p.forward_from else None,
            }
        )
    return out


async def pending_extract_ids(tenant_id: int, limit: int = BATCH_SIZE) -> list[int]:
    """Posts with no successful extraction at the current version."""
    async with session_scope() as db:
        done = select(Extraction.post_id).where(
            Extraction.tenant_id == tenant_id,
            Extraction.extractor_version == EXTRACTOR_VERSION,
            Extraction.status.in_(["succeeded", "submitted", "queued"]),
        )
        return list(
            (
                await db.scalars(
                    select(Post.id)
                    .where(
                        Post.tenant_id == tenant_id,
                        Post.is_deleted.is_(False),
                        Post.is_album_root.is_(True),
                        Post.id.not_in(done),
                        func.length(Post.text) > 0,
                    )
                    .order_by(Post.date.desc())
                    .limit(limit)
                )
            ).all()
        )


async def estimate_cost(tenant_id: int, sample: int = 10) -> dict[str, Any]:
    """Token-count a sample and extrapolate, so the admin sees the bill before a batch is submitted."""
    from kanalchi.ai.claude import count_tokens

    s = get_settings()
    system, channel_title = await build_prompt(tenant_id)
    ids = await pending_extract_ids(tenant_id, limit=sample)
    if not ids:
        return {"posts": 0, "estimated_usd": 0.0}
    async with session_scope() as db:
        posts = await _posts_payload(db, ids, channel_title)
        total = await db.scalar(
            select(func.count())
            .select_from(Post)
            .where(Post.tenant_id == tenant_id, Post.is_deleted.is_(False), Post.is_album_root.is_(True))
        )
    counts = [await count_tokens(s.extract_model, system, prompts.extraction_user(p)) for p in posts]
    avg_in = sum(counts) / len(counts)
    pending = len(await pending_extract_ids(tenant_id, limit=100000))

    # Output dominates the bill: it is priced five times input, and adaptive
    # thinking is billed as output too. Guessing it badly under-quotes the job —
    # a flat 300 here quoted $35 for work that cost $32 for its first four-tenths.
    # Measure it from this channel's own completed extractions when there are any.
    avg_out = await db_avg_output(tenant_id) or DEFAULT_OUTPUT_TOKENS
    per_post = cost_usd(
        s.extract_model, Usage(input_tokens=int(avg_in), output_tokens=int(avg_out)), batch=True
    )
    return {
        "posts_total": total or 0,
        "posts_pending": pending,
        "avg_input_tokens": int(avg_in),
        "avg_output_tokens": int(avg_out),
        "output_measured": avg_out is not None,
        "estimated_usd": round(per_post * pending, 2),
        "model": s.extract_model,
    }


async def db_avg_output(tenant_id: int) -> float | None:
    """Mean output tokens across this channel's succeeded extractions, if any have run."""
    async with session_scope() as db:
        return await db.scalar(
            select(func.avg(cast(Extraction.usage["output_tokens"].astext, Float))).where(
                Extraction.tenant_id == tenant_id,
                Extraction.status == "succeeded",
                Extraction.usage.is_not(None),
            )
        )


async def submit_batch(tenant_id: int, post_ids: list[int] | None = None) -> dict[str, Any]:
    """Submit up to BATCH_SIZE posts. Returns {} when there is nothing to do or too many batches are in flight."""
    s = get_settings()
    async with session_scope() as db:
        in_flight = await db.scalar(
            select(func.count())
            .select_from(LlmBatch)
            .where(LlmBatch.status.in_(["submitted", "in_progress"]))
        )
    if (in_flight or 0) >= MAX_IN_FLIGHT:
        return {"skipped": "too many batches in flight", "in_flight": in_flight}

    ids = post_ids or await pending_extract_ids(tenant_id)
    if not ids:
        return {"posts": 0}
    ids = ids[:BATCH_SIZE]

    system, channel_title = await build_prompt(tenant_id)
    async with session_scope() as db:
        posts = await _posts_payload(db, ids, channel_title)
    requests = [_request(p, system, s.extract_model) for p in posts]

    batch = await get_client().messages.batches.create(requests=requests)
    async with session_scope() as db:
        row = LlmBatch(
            tenant_id=tenant_id,
            anthropic_batch_id=batch.id,
            purpose="extract",
            model=s.extract_model,
            status="submitted",
            request_count=len(requests),
            submitted_at=datetime.now(UTC),
        )
        db.add(row)
        await db.flush()
        for p in posts:
            stmt = insert(Extraction).values(
                tenant_id=tenant_id,
                post_id=p["id"],
                extractor_version=EXTRACTOR_VERSION,
                model=s.extract_model,
                prompt_version=EXTRACT_PROMPT_VERSION,
                llm_batch_id=row.id,
                custom_id=custom_id(p["id"]),
                status="submitted",
            )
            await db.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_extractions_post_version",
                    set_={
                        "llm_batch_id": row.id,
                        "status": "submitted",
                        "custom_id": stmt.excluded.custom_id,
                    },
                )
            )
        batch_row_id = row.id
    log.info("extract.batch_submitted", tenant_id=tenant_id, batch=batch.id, posts=len(requests))
    return {"batch_id": batch.id, "llm_batch_id": batch_row_id, "posts": len(requests)}


async def poll_batches() -> list[int]:
    """Refresh in-flight batch statuses. Returns the ids of batches that just ended."""
    async with session_scope() as db:
        rows = (
            await db.scalars(select(LlmBatch).where(LlmBatch.status.in_(["submitted", "in_progress"])))
        ).all()
        pending = [(r.id, r.anthropic_batch_id) for r in rows]
    ended: list[int] = []
    for row_id, batch_id in pending:
        batch = await get_client().messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        async with session_scope() as db:
            row = await db.get(LlmBatch, row_id)
            row.status = "ended" if batch.processing_status == "ended" else batch.processing_status
            row.succeeded = counts.succeeded
            row.errored = counts.errored
            row.expired = counts.expired
            if batch.processing_status == "ended":
                row.ended_at = datetime.now(UTC)
                ended.append(row_id)
    return ended


async def ingest_results(llm_batch_id: int) -> dict[str, Any]:
    """Stream batch results, validate, persist, and queue follow-up work."""
    async with session_scope() as db:
        row = await db.get(LlmBatch, llm_batch_id)
        if row is None or row.ingested_at is not None:
            return {"skipped": True}
        batch_id, tenant_id, model = row.anthropic_batch_id, row.tenant_id, row.model

    ok = refused = invalid = retry = 0
    total_usage = Usage()
    parsed_posts: list[int] = []

    async for result in await get_client().messages.batches.results(batch_id):
        post_id = parse_custom_id(result.custom_id)
        if post_id is None:
            continue
        kind = result.result.type
        if kind == "succeeded":
            message = result.result.message
            usage = Usage.from_response(message.usage)
            total_usage = Usage(
                input_tokens=total_usage.input_tokens + usage.input_tokens,
                output_tokens=total_usage.output_tokens + usage.output_tokens,
                cache_write_tokens=total_usage.cache_write_tokens + usage.cache_write_tokens,
                cache_read_tokens=total_usage.cache_read_tokens + usage.cache_read_tokens,
            )
            if message.stop_reason == "refusal":
                await _mark(post_id, "refused", error="model declined this post")
                refused += 1
                continue
            text = next((b.text for b in message.content if b.type == "text"), "")
            try:
                data = PostExtraction.model_validate_json(text).model_dump()
            except Exception as exc:  # noqa: BLE001
                await _mark(post_id, "invalid", error=str(exc)[:500])
                invalid += 1
                continue
            await _store(post_id, data, usage, model)
            parsed_posts.append(post_id)
            ok += 1
        elif kind in {"errored", "expired", "canceled"}:
            err = getattr(result.result, "error", None)
            err_type = getattr(err, "type", kind)
            if err_type == "invalid_request":
                await _mark(post_id, "invalid", error=str(err)[:500])
                invalid += 1
            else:
                await _mark(post_id, "queued", error=f"{kind}: retrying", bump_attempt=True)
                retry += 1

    usd = await record_usage(tenant_id, model, "extract", total_usage, batch=True, requests=ok)
    async with session_scope() as db:
        row = await db.get(LlmBatch, llm_batch_id)
        row.ingested_at = datetime.now(UTC)
        row.cost_usd = usd
    log.info(
        "extract.ingested",
        batch=batch_id,
        ok=ok,
        refused=refused,
        invalid=invalid,
        retry=retry,
        usd=round(usd, 4),
    )
    return {
        "ok": ok,
        "refused": refused,
        "invalid": invalid,
        "retry": retry,
        "cost_usd": usd,
        "posts": parsed_posts,
    }


async def _mark(post_id: int, status: str, *, error: str | None = None, bump_attempt: bool = False) -> None:
    async with session_scope() as db:
        ext = await db.scalar(
            select(Extraction).where(
                Extraction.post_id == post_id, Extraction.extractor_version == EXTRACTOR_VERSION
            )
        )
        if ext is None:
            return
        ext.status = status
        ext.error = error
        if bump_attempt:
            ext.attempts = (ext.attempts or 0) + 1
            if ext.attempts >= MAX_ATTEMPTS:
                ext.status = "errored"


async def _store(post_id: int, data: dict[str, Any], usage: Usage, model: str) -> None:
    from kanalchi.ai.postprocess import apply_extraction

    async with session_scope() as db:
        ext = await db.scalar(
            select(Extraction).where(
                Extraction.post_id == post_id, Extraction.extractor_version == EXTRACTOR_VERSION
            )
        )
        if ext is None:
            return
        ext.status = "succeeded"
        ext.result = data
        ext.usage = usage.as_dict()
        ext.cost_usd = cost_usd(model, usage, batch=True)
        ext.error = None
        await db.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(
                title=(data.get("title") or None),
                summary=(data.get("summary") or None),
                language=data.get("language_primary"),
                extraction_version=EXTRACTOR_VERSION,
                index_status="extracted",
            )
        )
    await apply_extraction(post_id, data)


async def extract_one(post_id: int) -> dict[str, Any]:
    """Single synchronous extraction for a newly published post (incremental path, not batched)."""
    s = get_settings()
    async with session_scope() as db:
        post = await db.get(Post, post_id)
        if post is None or post.is_deleted or not (post.text or "").strip():
            return {"skipped": True}
        tenant_id = post.tenant_id
        channel = await db.get(Channel, post.channel_id)
        payload = (await _posts_payload(db, [post_id], channel.title if channel else ""))[0]
    system, _ = await build_prompt(tenant_id)

    message = await get_client().messages.create(
        model=s.extract_model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": prompts.extraction_user(payload)}],
        thinking={"type": "adaptive"},
        output_config={"effort": "low", "format": json_format(schema_of(PostExtraction))},
    )
    usage = Usage.from_response(message.usage)
    await record_usage(tenant_id, s.extract_model, "extract", usage)
    if message.stop_reason == "refusal":
        return {"refused": True}
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        data = PostExtraction.model_validate_json(text).model_dump()
    except Exception as exc:  # noqa: BLE001
        log.warning("extract.invalid", post_id=post_id, error=str(exc)[:200])
        return {"invalid": True}

    async with session_scope() as db:
        stmt = insert(Extraction).values(
            tenant_id=tenant_id,
            post_id=post_id,
            extractor_version=EXTRACTOR_VERSION,
            model=s.extract_model,
            prompt_version=EXTRACT_PROMPT_VERSION,
            status="queued",
        )
        await db.execute(stmt.on_conflict_do_nothing(constraint="uq_extractions_post_version"))
    await _store(post_id, data, usage, s.extract_model)
    return {"ok": True}


def extraction_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)
