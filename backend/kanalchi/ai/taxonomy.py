"""Taxonomy build and apply.

Three passes:
  A  aggregate every extracted value per dimension into `tag_candidates` (pure SQL, no model)
  B  Opus clusters each dimension's candidates into canonical tags with aliases (chunked, streamed)
  C  apply the proposal idempotently, then re-assign posts

Manual edits always win in pass C: a pinned label is never overwritten, a merged tag is never
re-split, a hidden tag stays hidden, and a human-added alias is never dropped. That is what makes a
rebuild safe to run on a channel someone has already curated.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from kanalchi.ai import prompts
from kanalchi.ai.claude import complete_json, system_blocks
from kanalchi.ai.schemas import TaxonomyProposal, schema_of
from kanalchi.core.db import session_scope
from kanalchi.core.jobs import update_job_run
from kanalchi.core.logging import get_logger
from kanalchi.core.models import (
    Dimension,
    Extraction,
    Post,
    PostTag,
    Tag,
    TagAlias,
    TagCandidate,
    TaxonomyVersion,
    Tenant,
)
from kanalchi.core.settings import get_settings
from kanalchi.text.normalize import normalize
from kanalchi.text.slug import slugify

log = get_logger(__name__)

# Each proposed tag costs roughly 130 output tokens — canonical name, three
# labels, aliases, description, parent, merged candidates. Three hundred of them
# overran a 32k ceiling and every chunk came back truncated.
CHUNK = 100
# Per dimension. A browsable index wants a few hundred subjects, not a thousand.
MAX_CANDIDATES = 400
MIN_COUNT_ENTITY = 1
MIN_COUNT_THEME = 3

# Dimensions whose values come from the model and therefore need canonicalizing.
OPEN_DIMENSIONS = (
    "themes",
    "people",
    "gov_orgs",
    "orgs",
    "products",
    "locations",
    "events",
    "laws",
    "media_outlets",
)


# --------------------------------------------------------------------- pass A
AGGREGATE_SQL = text(
    """
WITH entity_rows AS (
    SELECT e->>'type'        AS etype,
           e->>'normalized'  AS name,
           e->>'surface'     AS surface,
           e->>'lang'        AS lang,
           x.post_id         AS post_id,
           p.engagement_score AS engagement
    FROM extractions x
    JOIN posts p ON p.id = x.post_id
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(x.result->'entities', '[]'::jsonb)) AS e
    WHERE x.tenant_id = :tenant_id AND x.status = 'succeeded'
),
theme_rows AS (
    SELECT 'theme'          AS etype,
           t->>'name'       AS name,
           t->>'name'       AS surface,
           NULL             AS lang,
           x.post_id        AS post_id,
           p.engagement_score AS engagement
    FROM extractions x
    JOIN posts p ON p.id = x.post_id
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(x.result->'themes', '[]'::jsonb)) AS t
    WHERE x.tenant_id = :tenant_id AND x.status = 'succeeded'
),
custom_rows AS (
    SELECT c->>'dimension'  AS etype,
           v                AS name,
           v                AS surface,
           NULL             AS lang,
           x.post_id        AS post_id,
           p.engagement_score AS engagement
    FROM extractions x
    JOIN posts p ON p.id = x.post_id
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(x.result->'custom', '[]'::jsonb)) AS c
    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(c->'values', '[]'::jsonb)) AS v
    WHERE x.tenant_id = :tenant_id AND x.status = 'succeeded'
),
all_rows AS (
    SELECT * FROM entity_rows UNION ALL SELECT * FROM theme_rows UNION ALL SELECT * FROM custom_rows
)
SELECT etype,
       name,
       count(*)                              AS cnt,
       (array_agg(DISTINCT surface))[1:8]    AS surfaces,
       (array_agg(DISTINCT post_id))[1:5]    AS sample_post_ids,
       max(lang)                             AS lang,
       avg(engagement)                       AS mean_engagement
FROM all_rows
WHERE name IS NOT NULL AND length(trim(name)) > 1
GROUP BY etype, name
ORDER BY cnt DESC
"""
)

ENTITY_TYPE_TO_DIMENSION = {
    "person": "people",
    "gov_org": "gov_orgs",
    "org": "orgs",
    "product": "products",
    "location": "locations",
    "event": "events",
    "law": "laws",
    "media_outlet": "media_outlets",
    "tg_channel": "media_outlets",
    "theme": "themes",
}


async def aggregate_candidates(tenant_id: int) -> dict[str, int]:
    """Pass A: refresh `tag_candidates` from every successful extraction."""
    async with session_scope() as db:
        dims = {
            k: v
            for k, v in (
                await db.execute(select(Dimension.key, Dimension.id).where(Dimension.tenant_id == tenant_id))
            ).all()
        }
        rows = (await db.execute(AGGREGATE_SQL, {"tenant_id": tenant_id})).all()

        counts: dict[str, int] = {}
        for etype, name, cnt, surfaces, sample_ids, lang, mean_engagement in rows:
            dim_key = ENTITY_TYPE_TO_DIMENSION.get(etype, etype)
            dim_id = dims.get(dim_key)
            if dim_id is None:
                continue
            norm = normalize(name)
            if not norm:
                continue
            stmt = insert(TagCandidate).values(
                tenant_id=tenant_id,
                dimension_id=dim_id,
                name=name.strip()[:200],
                name_norm=norm[:200],
                lang=lang,
                count=cnt,
                sample_post_ids=list(sample_ids or []),
                surface_forms=[s[:200] for s in (surfaces or []) if s][:8],
                mean_engagement=float(mean_engagement or 0),
                status="pending",
                last_seen_at=datetime.now(UTC),
            )
            await db.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_tag_candidates_tenant_dim_norm",
                    set_={
                        "count": stmt.excluded.count,
                        "surface_forms": stmt.excluded.surface_forms,
                        "sample_post_ids": stmt.excluded.sample_post_ids,
                        "mean_engagement": stmt.excluded.mean_engagement,
                        "last_seen_at": stmt.excluded.last_seen_at,
                    },
                )
            )
            counts[dim_key] = counts.get(dim_key, 0) + 1
    log.info(
        "taxonomy.aggregated", tenant_id=tenant_id, dimensions=len(counts), candidates=sum(counts.values())
    )
    return counts


# --------------------------------------------------------------------- pass B
def _min_count(dimension_key: str) -> int:
    floor = get_settings().taxonomy_min_count
    return max(floor, MIN_COUNT_THEME if dimension_key == "themes" else MIN_COUNT_ENTITY)


async def _candidates_for(db, tenant_id: int, dim_id: int, dim_key: str) -> list[dict[str, Any]]:
    floor = _min_count(dim_key)
    rows = (
        await db.execute(
            select(TagCandidate)
            .where(
                TagCandidate.tenant_id == tenant_id,
                TagCandidate.dimension_id == dim_id,
                TagCandidate.status.in_(["pending", "promoted"]),
            )
            .order_by(TagCandidate.count.desc(), TagCandidate.mean_engagement.desc())
            .limit(MAX_CANDIDATES * 2)
        )
    ).scalars()
    rows = list(rows)
    # Rare-but-notable values earn a place: one mention on a post that went far
    # still matters. "High engagement" has to mean high *for this channel*, though —
    # the column holds a raw score averaging over a thousand here, so comparing it
    # to 1.0 admitted 38,999 of 39,005 candidates and made the floor a no-op.
    scores = sorted((c.mean_engagement or 0.0) for c in rows)
    notable = scores[int(len(scores) * 0.9)] if scores else 0.0

    out = []
    for c in rows:
        if c.count < floor and (c.mean_engagement or 0.0) < notable:
            continue
        out.append({"name": c.name, "count": c.count, "surface_forms": c.surface_forms or []})
        if len(out) >= MAX_CANDIDATES:
            break
    return out


async def _existing_tags(db, tenant_id: int, dim_id: int) -> list[dict[str, Any]]:
    tags = (
        await db.scalars(
            select(Tag).where(Tag.tenant_id == tenant_id, Tag.dimension_id == dim_id, Tag.status != "merged")
        )
    ).all()
    if not tags:
        return []
    aliases = (
        await db.execute(
            select(TagAlias.tag_id, TagAlias.alias).where(TagAlias.tag_id.in_([t.id for t in tags]))
        )
    ).all()
    by_tag: dict[int, list[str]] = {}
    for tag_id, alias in aliases:
        by_tag.setdefault(tag_id, []).append(alias)
    return [{"canonical_name": t.canonical_name, "aliases": by_tag.get(t.id, [])} for t in tags]


async def build(tenant_id: int, job_run_id: int | None = None) -> dict[str, Any]:
    """Passes A and B. Writes a `proposed` taxonomy version; apply() commits it."""
    await aggregate_candidates(tenant_id)

    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        profile = (tenant.settings or {}).get("channel_profile")
        dims = (
            await db.scalars(
                select(Dimension)
                .where(
                    Dimension.tenant_id == tenant_id,
                    Dimension.kind == "open",
                    Dimension.is_visible.is_(True),
                )
                .order_by(Dimension.sort_order)
            )
        ).all()
        last = await db.scalar(
            select(func.max(TaxonomyVersion.version_no)).where(TaxonomyVersion.tenant_id == tenant_id)
        )
        version = TaxonomyVersion(
            tenant_id=tenant_id,
            version_no=(last or 0) + 1,
            status="building",
            # What actually built it — this row is the audit trail for a proposal
            # someone may apply months later, so it must not claim a model we
            # did not use.
            model=get_settings().taxonomy_model,
            built_at=datetime.now(UTC),
        )
        db.add(version)
        await db.flush()
        version_id, version_no = version.id, version.version_no
        dim_list = [(d.id, d.key, d.description or d.extraction_hint or d.key) for d in dims]

    proposal: dict[str, Any] = {}
    stats: dict[str, Any] = {}
    total_cost = 0.0

    gate = asyncio.Semaphore(get_settings().taxonomy_concurrency)
    completed = 0

    async def run_dimension(i: int, dim_id: int, dim_key: str, description: str) -> None:
        nonlocal total_cost, completed
        async with gate:
            await _build_dimension(i, dim_id, dim_key, description)
        completed += 1

    async def _build_dimension(i: int, dim_id: int, dim_key: str, description: str) -> None:
        nonlocal total_cost
        async with session_scope() as db:
            candidates = await _candidates_for(db, tenant_id, dim_id, dim_key)
            existing = await _existing_tags(db, tenant_id, dim_id)
        if not candidates:
            return
        await update_job_run(
            job_run_id,
            progress={
                "stage": f"dimension {dim_key}",
                "done": completed,
                "total": len(dim_list),
                "message": f"{len(candidates)} candidates",
            },
        )

        tags: list[dict[str, Any]] = []
        dropped: list[str] = []
        proposed_names: list[str] = []
        for start in range(0, len(candidates), CHUNK):
            chunk = candidates[start : start + CHUNK]
            result, cost = await complete_json(
                tenant_id=tenant_id,
                purpose="taxonomy",
                system=system_blocks(prompts.TAXONOMY_SYSTEM),
                user=prompts.taxonomy_user(dim_key, description, chunk, existing, proposed_names, profile),
                schema=schema_of(TaxonomyProposal),
                model=get_settings().taxonomy_model,
                # Consolidating a list is not deep reasoning, and thinking is billed
                # as output and counted against the same ceiling.
                effort="medium",
                max_tokens=64000,
            )
            total_cost += cost
            if not result:
                log.warning("taxonomy.chunk_failed", tenant_id=tenant_id, dimension=dim_key, start=start)
                continue  # noqa: PERF203 — one bad chunk must not lose the dimension
            tags.extend(result.get("tags") or [])
            dropped.extend(result.get("dropped_candidates") or [])
            proposed_names = [t["canonical_name"] for t in tags]
            # Persist partial progress so a crash mid-build does not lose completed chunks.
            async with session_scope() as db:
                v = await db.get(TaxonomyVersion, version_id)
                v.proposal = {**(v.proposal or {}), dim_key: {"tags": tags, "dropped_candidates": dropped}}
                v.cost_usd = total_cost

        proposal[dim_key] = {"tags": tags, "dropped_candidates": dropped}
        stats[dim_key] = {"candidates": len(candidates), "tags": len(tags), "dropped": len(dropped)}

    # A dimension that dies takes its own chunks down, not the whole build: every
    # completed chunk is already persisted, and forty calls are too expensive to
    # discard because the last connection dropped.
    outcomes = await asyncio.gather(
        *(run_dimension(i, *d) for i, d in enumerate(dim_list)), return_exceptions=True
    )
    for (_, dim_key, _), outcome in zip(dim_list, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            log.warning("taxonomy.dimension_failed", dimension=dim_key, error=str(outcome)[:200])

    async with session_scope() as db:
        v = await db.get(TaxonomyVersion, version_id)
        v.proposal = proposal
        v.candidate_stats = stats
        v.cost_usd = total_cost
        v.status = "proposed"
    log.info(
        "taxonomy.built", tenant_id=tenant_id, version=version_no, cost=round(total_cost, 4), dims=len(stats)
    )
    return {"version_id": version_id, "version_no": version_no, "stats": stats, "cost_usd": total_cost}


# --------------------------------------------------------------------- pass C
async def apply(tenant_id: int, version_id: int, job_run_id: int | None = None) -> dict[str, Any]:
    """Merge a proposal into `tags`, honouring manual edits, then re-assign every post."""
    async with session_scope() as db:
        version = await db.get(TaxonomyVersion, version_id)
        if version is None or version.tenant_id != tenant_id:
            raise RuntimeError("taxonomy version not found")
        if version.status == "applied":
            return {"skipped": "already applied"}
        proposal = version.proposal or {}
        version_no = version.version_no
        dims = {
            k: v
            for k, v in (
                await db.execute(select(Dimension.key, Dimension.id).where(Dimension.tenant_id == tenant_id))
            ).all()
        }

    diff: dict[str, Any] = {"created": [], "updated": [], "hidden": [], "aliases_added": 0}

    for dim_key, payload in proposal.items():
        dim_id = dims.get(dim_key)
        if dim_id is None:
            continue
        seen_tag_ids: set[int] = set()
        parents: list[tuple[int, str]] = []

        async with session_scope() as db:
            for proposed in payload.get("tags", []):
                canonical = (proposed.get("canonical_name") or "").strip()
                if not canonical:
                    continue
                norm = normalize(canonical)[:200]
                labels = {
                    "uz": proposed.get("label_uz") or canonical,
                    "ru": proposed.get("label_ru") or canonical,
                    "en": proposed.get("label_en") or canonical,
                }
                aliases = [a for a in (proposed.get("aliases") or []) if a and a.strip()]
                aliases += [m for m in (proposed.get("merged_candidates") or []) if m and m.strip()]

                tag = await _resolve_existing(db, tenant_id, dim_id, norm, aliases)
                if tag is None:
                    tag = Tag(
                        tenant_id=tenant_id,
                        dimension_id=dim_id,
                        slug=await _unique_slug(db, tenant_id, canonical),
                        canonical_name=canonical[:200],
                        canonical_norm=norm,
                        labels=labels,
                        description=(proposed.get("description") or "")[:500] or None,
                        status="active",
                        source="taxonomy",
                        first_seen_version=version_no,
                        last_seen_version=version_no,
                    )
                    db.add(tag)
                    await db.flush()
                    diff["created"].append(canonical)
                else:
                    if tag.status == "merged" and tag.merged_into_id:
                        merged_target = await db.get(Tag, tag.merged_into_id)
                        if merged_target is not None:
                            tag = merged_target  # never re-split what a human merged
                    if not tag.is_pinned:  # a pinned tag keeps the name and labels a human chose
                        tag.labels = {**(tag.labels or {}), **labels}
                        tag.description = (proposed.get("description") or tag.description or "")[:500] or None
                    if tag.status == "hidden" and not tag.is_pinned:
                        tag.status = "active"
                    tag.last_seen_version = version_no
                    diff["updated"].append(tag.canonical_name)

                seen_tag_ids.add(tag.id)
                for alias in dict.fromkeys([canonical, *aliases]):
                    alias_norm = normalize(alias)[:200]
                    if not alias_norm:
                        continue
                    stmt = insert(TagAlias).values(
                        tenant_id=tenant_id,
                        tag_id=tag.id,
                        alias=alias[:200],
                        alias_norm=alias_norm,
                        source="llm",
                    )
                    res = await db.execute(
                        stmt.on_conflict_do_nothing(constraint="uq_tag_aliases_tag_norm").returning(
                            TagAlias.id
                        )
                    )
                    if res.scalar() is not None:
                        diff["aliases_added"] += 1
                if proposed.get("parent_canonical"):
                    parents.append((tag.id, normalize(proposed["parent_canonical"])[:200]))

            # hierarchy, second pass so parents exist
            for child_id, parent_norm in parents:
                parent_id = await db.scalar(
                    select(Tag.id).where(
                        Tag.tenant_id == tenant_id,
                        Tag.dimension_id == dim_id,
                        Tag.canonical_norm == parent_norm,
                    )
                )
                if parent_id and parent_id != child_id:
                    await db.execute(update(Tag).where(Tag.id == child_id).values(parent_id=parent_id))

            # tags the proposal dropped: hide, never delete, so old URLs keep resolving
            stale = (
                await db.scalars(
                    select(Tag).where(
                        Tag.tenant_id == tenant_id,
                        Tag.dimension_id == dim_id,
                        Tag.status == "active",
                        Tag.source == "taxonomy",
                        Tag.is_pinned.is_(False),
                        Tag.id.not_in(seen_tag_ids or {0}),
                    )
                )
            ).all()
            for t in stale:
                t.status = "hidden"
                diff["hidden"].append(t.canonical_name)

    await embed_tags(tenant_id)
    reassigned = await reassign_all(tenant_id, job_run_id=job_run_id)
    await recompute_counts(tenant_id)

    async with session_scope() as db:
        version = await db.get(TaxonomyVersion, version_id)
        version.status = "applied"
        version.applied_at = datetime.now(UTC)
        version.diff = diff
        tenant = await db.get(Tenant, tenant_id)
        tenant.active_taxonomy_version_id = version_id
        await db.execute(
            update(TaxonomyVersion)
            .where(
                TaxonomyVersion.tenant_id == tenant_id,
                TaxonomyVersion.id != version_id,
                TaxonomyVersion.status == "applied",
            )
            .values(status="archived")
        )
    log.info(
        "taxonomy.applied",
        tenant_id=tenant_id,
        version=version_no,
        created=len(diff["created"]),
        hidden=len(diff["hidden"]),
        reassigned=reassigned,
    )
    return {"version_id": version_id, "diff": diff, "reassigned": reassigned}


async def _resolve_existing(db, tenant_id: int, dim_id: int, norm: str, aliases: list[str]) -> Tag | None:
    tag = await db.scalar(
        select(Tag).where(Tag.tenant_id == tenant_id, Tag.dimension_id == dim_id, Tag.canonical_norm == norm)
    )
    if tag is not None:
        return tag
    alias_norms = [normalize(a)[:200] for a in aliases if normalize(a)]
    if not alias_norms:
        return None
    tag_id = await db.scalar(
        select(TagAlias.tag_id)
        .join(Tag, Tag.id == TagAlias.tag_id)
        .where(
            TagAlias.tenant_id == tenant_id, Tag.dimension_id == dim_id, TagAlias.alias_norm.in_(alias_norms)
        )
        .limit(1)
    )
    return await db.get(Tag, tag_id) if tag_id else None


async def _unique_slug(db, tenant_id: int, canonical: str) -> str:
    base = slugify(canonical)
    slug = base
    for suffix in range(1, 50):
        clash = await db.scalar(select(Tag.id).where(Tag.tenant_id == tenant_id, Tag.slug == slug))
        if not clash:
            return slug
        slug = f"{base}-{suffix}"
    return f"{base}-{datetime.now(UTC).timestamp():.0f}"


async def embed_tags(tenant_id: int) -> int:
    """Embed `canonical name + aliases` so the mapping cascade can match by similarity."""
    from kanalchi.ai.embeddings import embed

    async with session_scope() as db:
        tags = (
            await db.scalars(
                select(Tag).where(Tag.tenant_id == tenant_id, Tag.status == "active", Tag.embedding.is_(None))
            )
        ).all()
        if not tags:
            return 0
        alias_rows = (
            await db.execute(
                select(TagAlias.tag_id, TagAlias.alias).where(TagAlias.tag_id.in_([t.id for t in tags]))
            )
        ).all()
        by_tag: dict[int, list[str]] = {}
        for tag_id, alias in alias_rows:
            by_tag.setdefault(tag_id, []).append(alias)
        payload = [(t.id, ", ".join([t.canonical_name, *by_tag.get(t.id, [])][:8])) for t in tags]

    vectors, _ = await embed([p[1] for p in payload], input_type="document", tenant_id=tenant_id)
    async with session_scope() as db:
        for (tag_id, _), vector in zip(payload, vectors, strict=True):
            await db.execute(update(Tag).where(Tag.id == tag_id).values(embedding=vector))
    return len(payload)


async def reassign_all(tenant_id: int, job_run_id: int | None = None, batch: int = 200) -> int:
    """Re-run the assignment cascade for every extracted post against the active taxonomy."""
    from kanalchi.ai.postprocess import apply_extraction

    async with session_scope() as db:
        rows = (
            await db.execute(
                select(Extraction.post_id).where(
                    Extraction.tenant_id == tenant_id, Extraction.status == "succeeded"
                )
            )
        ).all()
    post_ids = [r[0] for r in rows]
    done = 0
    for start in range(0, len(post_ids), batch):
        chunk = post_ids[start : start + batch]
        async with session_scope() as db:
            results = (
                await db.execute(
                    select(Extraction.post_id, Extraction.result).where(Extraction.post_id.in_(chunk))
                )
            ).all()
        for post_id, data in results:
            if data:
                await apply_extraction(post_id, data)
                done += 1
        await update_job_run(job_run_id, progress={"stage": "reassign", "done": done, "total": len(post_ids)})
    return done


COUNTS_SQL = text(
    """
WITH stats AS (
    SELECT pt.tag_id,
           count(*)                    AS post_count,
           coalesce(avg(p.views), 0)   AS mean_views
    FROM post_tags pt
    JOIN posts p ON p.id = pt.post_id AND p.is_deleted = false
    WHERE pt.tenant_id = :tenant_id
    GROUP BY pt.tag_id
),
channel AS (
    SELECT nullif(avg(views), 0) AS mean_views FROM posts WHERE tenant_id = :tenant_id AND is_deleted = false
)
UPDATE tags t
SET post_count = coalesce(s.post_count, 0),
    engagement_score = coalesce(s.mean_views / nullif((SELECT mean_views FROM channel), 0), 0)
FROM (SELECT t2.id, s2.post_count, s2.mean_views
      FROM tags t2 LEFT JOIN stats s2 ON s2.tag_id = t2.id
      WHERE t2.tenant_id = :tenant_id) s
WHERE t.id = s.id
"""
)


async def recompute_counts(tenant_id: int) -> None:
    async with session_scope() as db:
        await db.execute(COUNTS_SQL, {"tenant_id": tenant_id})
        await db.execute(
            update(TagCandidate)
            .where(
                TagCandidate.tenant_id == tenant_id,
                TagCandidate.name_norm.in_(
                    select(Tag.canonical_norm).where(Tag.tenant_id == tenant_id, Tag.status == "active")
                ),
            )
            .values(status="promoted")
        )


async def taxonomy_summary(tenant_id: int, per_dimension: int = 40) -> str:
    """Compact digest of the active taxonomy for chat prompts (stable ordering for cache hits)."""
    async with session_scope() as db:
        rows = (
            await db.execute(
                select(Dimension.key, Tag.canonical_name, Tag.slug, Tag.post_count)
                .join(Tag, Tag.dimension_id == Dimension.id)
                .where(Tag.tenant_id == tenant_id, Tag.status == "active", Tag.post_count > 0)
                .order_by(Dimension.sort_order, Tag.post_count.desc())
            )
        ).all()
    by_dim: dict[str, list[str]] = {}
    for key, name, slug, count in rows:
        bucket = by_dim.setdefault(key, [])
        if len(bucket) < per_dimension:
            bucket.append(f"{name} [{slug}] ({count})")
    return json.dumps(by_dim, ensure_ascii=False, sort_keys=True, indent=0)


async def stale_post_count(tenant_id: int) -> int:
    async with session_scope() as db:
        return (
            await db.scalar(
                select(func.count())
                .select_from(Post)
                .where(
                    Post.tenant_id == tenant_id,
                    Post.is_deleted.is_(False),
                    Post.is_album_root.is_(True),
                    Post.index_status != "tagged",
                )
            )
            or 0
        )


async def orphan_tag_ids(tenant_id: int) -> list[int]:
    async with session_scope() as db:
        rows = (
            await db.execute(
                select(Tag.id)
                .outerjoin(PostTag, PostTag.tag_id == Tag.id)
                .where(Tag.tenant_id == tenant_id, Tag.status == "active")
                .group_by(Tag.id)
                .having(func.count(PostTag.post_id) == 0)
            )
        ).all()
    return [r[0] for r in rows]
