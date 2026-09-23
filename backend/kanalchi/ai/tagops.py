"""Hand-editing the index: promoting candidates, merging, hiding, asking for a rebuild.

These are the operations behind the console's Index page. They take a session and a tenant
id rather than a request, so whichever router exposes them decides who may call them; the
rule that manual edits pin a tag (and so survive the next rebuild) lives here, once.
"""

from __future__ import annotations

from typing import Any

from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.core.jobs import create_job_run
from kanalchi.core.models import Dimension, PostTag, Tag, TagAlias, TagCandidate
from kanalchi.jobs import index_jobs
from kanalchi.text.normalize import normalize


class TagOpError(Exception):
    """A refusal the caller turns into an HTTP status."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _distinct_forms(name: str, forms: list[str]) -> list[str]:
    """The spellings that differ from the name itself, once each — case and script folded."""
    seen = {normalize(name)}
    out: list[str] = []
    for form in forms:
        norm = normalize(form)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(form)
    return out


async def pending_candidates(db: AsyncSession, tenant_id: int, limit: int = 50) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(TagCandidate, Dimension.key)
            .join(Dimension, Dimension.id == TagCandidate.dimension_id)
            .where(TagCandidate.tenant_id == tenant_id, TagCandidate.status == "pending")
            .order_by(TagCandidate.count.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "dimension": key,
            "count": c.count,
            "surface_forms": _distinct_forms(c.name, c.surface_forms or []),
            "sample_post_ids": c.sample_post_ids or [],
        }
        for c, key in rows
    ]


async def hidden_tags(db: AsyncSession, tenant_id: int) -> list[tuple[Tag, str]]:
    """Tags taken off the site, so the decision can be reversed from the same page."""
    return list(
        (
            await db.execute(
                select(Tag, Dimension.key)
                .join(Dimension, Dimension.id == Tag.dimension_id)
                .where(Tag.tenant_id == tenant_id, Tag.status == "hidden")
                .order_by(Tag.post_count.desc())
                .limit(300)
            )
        ).all()
    )


async def edit_tag(
    db: AsyncSession,
    tenant_id: int,
    slug: str,
    *,
    labels: dict[str, str] | None = None,
    descriptions: dict[str, str] | None = None,
    hidden: bool | None = None,
) -> dict[str, Any]:
    """A manual edit pins the tag, which is what makes it survive the next taxonomy rebuild."""
    tag = await db.scalar(select(Tag).where(Tag.tenant_id == tenant_id, Tag.slug == slug))
    if tag is None:
        raise TagOpError(404, "tag not found")
    if labels:
        tag.labels = {**(tag.labels or {}), **labels}
        tag.is_pinned = True
    if descriptions is not None:
        tag.descriptions = {**(tag.descriptions or {}), **descriptions}
        tag.is_pinned = True
    if hidden is not None:
        tag.status = "hidden" if hidden else "active"
        tag.is_pinned = True
    return {"slug": tag.slug, "status": tag.status, "labels": tag.labels, "is_pinned": tag.is_pinned}


async def merge_tag(db: AsyncSession, tenant_id: int, slug: str, into: str) -> dict[str, Any]:
    """Fold one tag into another: its posts, its aliases and its old URL all follow."""
    source = await db.scalar(select(Tag).where(Tag.tenant_id == tenant_id, Tag.slug == slug))
    target = await db.scalar(select(Tag).where(Tag.tenant_id == tenant_id, Tag.slug == into))
    if source is None or target is None:
        raise TagOpError(404, "tag not found")
    if source.id == target.id:
        raise TagOpError(400, "a tag cannot be merged into itself")

    post_ids = (await db.scalars(select(PostTag.post_id).where(PostTag.tag_id == source.id))).all()
    existing = set((await db.scalars(select(PostTag.post_id).where(PostTag.tag_id == target.id))).all())
    for post_id in post_ids:
        if post_id not in existing:
            db.add(
                PostTag(
                    post_id=post_id, tag_id=target.id, tenant_id=tenant_id, confidence=1.0, source="manual"
                )
            )
    await db.execute(PostTag.__table__.delete().where(PostTag.tag_id == source.id))

    aliases = (await db.scalars(select(TagAlias).where(TagAlias.tag_id == source.id))).all()
    target_norms = set(
        (await db.scalars(select(TagAlias.alias_norm).where(TagAlias.tag_id == target.id))).all()
    )
    for alias in [*aliases]:
        if alias.alias_norm not in target_norms:
            db.add(
                TagAlias(
                    tenant_id=tenant_id,
                    tag_id=target.id,
                    alias=alias.alias,
                    alias_norm=alias.alias_norm,
                    lang=alias.lang,
                    source="merge",
                )
            )
            target_norms.add(alias.alias_norm)
    if source.canonical_norm not in target_norms:
        db.add(
            TagAlias(
                tenant_id=tenant_id,
                tag_id=target.id,
                alias=source.canonical_name,
                alias_norm=source.canonical_norm,
                source="merge",
            )
        )

    source.status = "merged"
    source.merged_into_id = target.id
    source.is_pinned = True
    target.is_pinned = True
    target.post_count = len(existing | set(post_ids))
    await index_jobs.recompute_counts.defer_async(tenant_id=tenant_id)
    return {"merged": source.slug, "into": target.slug, "posts_moved": len(post_ids)}


async def promote_candidate(db: AsyncSession, tenant_id: int, candidate_id: int) -> dict[str, Any]:
    """Turn a recurring unmatched value into a real tag, with its observed spellings as aliases."""
    from kanalchi.ai.postprocess import ensure_tag

    candidate = await db.get(TagCandidate, candidate_id)
    if candidate is None or candidate.tenant_id != tenant_id:
        raise TagOpError(404, "candidate not found")

    tag_id = await ensure_tag(db, tenant_id, candidate.dimension_id, candidate.name, source="manual")
    for alias in dict.fromkeys([candidate.name, *(candidate.surface_forms or [])]):
        alias_norm = normalize(alias)[:200]
        if not alias_norm:
            continue
        exists = await db.scalar(
            select(TagAlias.id).where(TagAlias.tag_id == tag_id, TagAlias.alias_norm == alias_norm)
        )
        if not exists:
            db.add(
                TagAlias(
                    tenant_id=tenant_id,
                    tag_id=tag_id,
                    alias=alias[:200],
                    alias_norm=alias_norm,
                    source="manual",
                )
            )
    candidate.status = "promoted"
    candidate.mapped_tag_id = tag_id
    tag = await db.get(Tag, tag_id)
    if tag is not None:
        tag.is_pinned = True
    await index_jobs.reassign.defer_async(tenant_id=tenant_id)
    return {"promoted": candidate.name, "tag_id": tag_id}


async def reject_candidate(db: AsyncSession, tenant_id: int, candidate_id: int) -> dict[str, Any]:
    candidate = await db.get(TagCandidate, candidate_id)
    if candidate is None or candidate.tenant_id != tenant_id:
        raise TagOpError(404, "candidate not found")
    candidate.status = "rejected"
    return {"ok": True}


async def request_rebuild(tenant_id: int, trigger: str) -> dict[str, Any]:
    """Propose a new taxonomy version. It is not applied until someone has read the diff."""
    try:
        job_run_id = await create_job_run(tenant_id, "taxonomy", {"trigger": trigger})
        await index_jobs.build_taxonomy.configure(queueing_lock=f"taxonomy:{tenant_id}").defer_async(
            tenant_id=tenant_id, job_run_id=job_run_id, auto_apply=False
        )
    except AlreadyEnqueued as exc:
        raise TagOpError(409, "a rebuild is already waiting to run") from exc
    return {"job_run_id": job_run_id}
