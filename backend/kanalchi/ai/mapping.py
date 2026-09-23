"""Assignment cascade: extracted values -> canonical tags.

Order matters and is deliberately cheap-first:
  1. alias match on the normalized form (free, exact)
  2. embedding similarity against tag vectors (cheap, catches spelling drift)
  3. a batched Sonnet call for the genuinely ambiguous middle band
  4. everything else lands in `tag_candidates` as a pending tag for a human to promote
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from kanalchi.core.logging import get_logger
from kanalchi.core.models import Dimension, PostTag, Tag, TagAlias, TagCandidate
from kanalchi.text.normalize import normalize

log = get_logger(__name__)

SIM_ASSIGN = 0.86  # at or above: assign directly
SIM_AMBIGUOUS = 0.72  # between the two: ask the model
MAX_NEAREST = 5


async def dimension_ids(db, tenant_id: int) -> dict[str, int]:
    rows = (
        await db.execute(select(Dimension.key, Dimension.id).where(Dimension.tenant_id == tenant_id))
    ).all()
    return {k: v for k, v in rows}


async def alias_index(db, tenant_id: int, dimension_id: int) -> dict[str, int]:
    """normalized alias -> tag id, for one dimension."""
    rows = (
        await db.execute(
            select(TagAlias.alias_norm, TagAlias.tag_id)
            .join(Tag, Tag.id == TagAlias.tag_id)
            .where(TagAlias.tenant_id == tenant_id, Tag.dimension_id == dimension_id, Tag.status == "active")
        )
    ).all()
    index = {a: t for a, t in rows}
    canon = (
        await db.execute(
            select(Tag.canonical_norm, Tag.id).where(
                Tag.tenant_id == tenant_id, Tag.dimension_id == dimension_id, Tag.status == "active"
            )
        )
    ).all()
    for norm, tid in canon:
        index.setdefault(norm, tid)
    return index


async def assign(
    db,
    tenant_id: int,
    post_id: int,
    tag_id: int,
    *,
    source: str,
    confidence: float = 1.0,
    evidence: dict[str, Any] | None = None,
) -> None:
    stmt = insert(PostTag).values(
        post_id=post_id,
        tag_id=tag_id,
        tenant_id=tenant_id,
        confidence=confidence,
        source=source,
        evidence=evidence,
    )
    await db.execute(stmt.on_conflict_do_nothing(index_elements=[PostTag.post_id, PostTag.tag_id]))


async def record_candidate(
    db,
    tenant_id: int,
    dimension_id: int,
    name: str,
    *,
    post_id: int,
    surface: str | None = None,
    lang: str | None = None,
) -> None:
    """Accumulate an unmatched value; it surfaces in the pending-tags queue once it recurs."""
    norm = normalize(name)
    if not norm:
        return
    stmt = insert(TagCandidate).values(
        tenant_id=tenant_id,
        dimension_id=dimension_id,
        name=name[:200],
        name_norm=norm[:200],
        lang=lang,
        count=1,
        sample_post_ids=[post_id],
        surface_forms=[surface[:200]] if surface else [],
        status="pending",
        last_seen_at=func.now(),
    )
    await db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_tag_candidates_tenant_dim_norm",
            set_={
                "count": TagCandidate.__table__.c.count + 1,
                "last_seen_at": func.now(),
                # Keep a bounded sample of where the candidate was seen. Written as
                # SQL because a Postgres array slice needs literal bounds: rendered
                # through the ORM the bounds come out as bind parameters and the
                # server rejects `array[$1:$2]` outright.
                "sample_post_ids": text(
                    "(array_cat(tag_candidates.sample_post_ids, excluded.sample_post_ids))[1:5]"
                ),
                # A spelling already on record is not appended again, or the list would be
                # eight copies of the same form by the time anyone looked at it.
                "surface_forms": text(
                    "CASE WHEN excluded.surface_forms <@ tag_candidates.surface_forms"
                    " THEN tag_candidates.surface_forms"
                    " ELSE (array_cat(tag_candidates.surface_forms, excluded.surface_forms))[1:8] END"
                ),
            },
        )
    )


async def nearest_tags(
    db, tenant_id: int, dimension_id: int, vector: list[float], limit: int = MAX_NEAREST
) -> list[tuple[int, str, float]]:
    """(tag_id, canonical_name, cosine similarity) for the closest tags in one dimension."""
    distance = Tag.embedding.cosine_distance(vector)
    rows = (
        await db.execute(
            select(Tag.id, Tag.canonical_name, distance.label("d"))
            .where(
                Tag.tenant_id == tenant_id,
                Tag.dimension_id == dimension_id,
                Tag.status == "active",
                Tag.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(limit)
        )
    ).all()
    return [(tid, name, 1.0 - float(d)) for tid, name, d in rows]


def extraction_values(data: dict[str, Any]) -> list[tuple[str, str, str, str | None]]:
    """Flatten an extraction into (dimension_key, normalized_name, surface, lang) tuples."""
    out: list[tuple[str, str, str, str | None]] = []
    type_to_dim = {
        "person": "people",
        "gov_org": "gov_orgs",
        "org": "orgs",
        "product": "products",
        "location": "locations",
        "event": "events",
        "law": "laws",
        "media_outlet": "media_outlets",
        "tg_channel": "media_outlets",
    }
    for e in data.get("entities") or []:
        dim = type_to_dim.get(e.get("type", ""))
        if not dim:
            continue
        name = (e.get("normalized") or e.get("surface") or "").strip()
        if name:
            out.append((dim, name, e.get("surface") or name, e.get("lang")))
    for t in data.get("themes") or []:
        name = (t.get("name") or "").strip()
        if name:
            out.append(("themes", name, name, None))
    for c in data.get("custom") or []:
        dim = c.get("dimension") or ""
        for v in c.get("values") or []:
            if v and v.strip():
                out.append((dim, v.strip(), v.strip(), None))
    return out
