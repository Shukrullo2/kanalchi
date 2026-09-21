"""Hybrid search: pgvector cosine + Postgres full text + trigram, fused with reciprocal rank fusion.

Why all three: the archive mixes Uzbek Latin, Uzbek Cyrillic, Russian and English inside one channel.
Full text alone misses a Cyrillic post when the query is Latin; vectors alone miss exact names and
rare strings. Trigram on the transliterated column catches typos and spelling drift. RRF fuses the
rankings without needing the scores to be on the same scale.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import text

from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger

log = get_logger(__name__)

RRF_K = 60
POOL = 60

Sort = Literal["relevance", "newest", "oldest", "views", "reactions"]

SEARCH_SQL = text(
    """
WITH filtered AS (
    SELECT p.id
    FROM posts p
    WHERE p.tenant_id = :tenant_id
      AND p.is_deleted = false
      AND p.is_album_root = true
      AND (CAST(:date_from AS timestamptz) IS NULL OR p.date >= :date_from)
      AND (CAST(:date_to AS timestamptz) IS NULL OR p.date <= :date_to)
      AND (CAST(:media_kind AS text) IS NULL OR p.media_kind = :media_kind)
      AND (:tag_count = 0 OR (
            SELECT count(DISTINCT t.id)
            FROM post_tags pt JOIN tags t ON t.id = pt.tag_id
            WHERE pt.post_id = p.id AND t.slug = ANY(:tag_slugs)
          ) = :tag_count)
),
vec AS (
    SELECT c.post_id,
           row_number() OVER (ORDER BY min(c.embedding <=> CAST(:qvec AS halfvec))) AS rank
    FROM post_chunks c
    JOIN filtered f ON f.id = c.post_id
    WHERE CAST(:qvec AS text) IS NOT NULL AND c.tenant_id = :tenant_id AND c.embedding IS NOT NULL
    GROUP BY c.post_id
    ORDER BY min(c.embedding <=> CAST(:qvec AS halfvec))
    LIMIT :pool
),
fts AS (
    -- The tsvector indexes the post as written AND its transliterated form, so a Cyrillic query
    -- matches a Latin post (and the other way round) once both are run through the same normalizer.
    SELECT p.id AS post_id,
           row_number() OVER (ORDER BY ts_rank_cd(p.tsv, q.query) DESC) AS rank
    FROM posts p
    JOIN filtered f ON f.id = p.id
    CROSS JOIN LATERAL (
        SELECT websearch_to_tsquery('simple', :query) || websearch_to_tsquery('simple', :query_norm) AS query
    ) AS q
    WHERE p.tsv @@ q.query
    ORDER BY ts_rank_cd(p.tsv, q.query) DESC
    LIMIT :pool
),
trgm AS (
    -- word_similarity, not similarity: the query is short and the post is long, so we want the best
    -- matching run of words inside the post rather than a whole-string comparison.
    SELECT p.id AS post_id,
           row_number() OVER (ORDER BY word_similarity(:query_norm, p.text_norm) DESC) AS rank
    FROM posts p
    JOIN filtered f ON f.id = p.id
    WHERE :query_norm <> '' AND word_similarity(:query_norm, p.text_norm) > 0.6
    ORDER BY word_similarity(:query_norm, p.text_norm) DESC
    LIMIT :pool
),
alias_hits AS (
    -- A query can name an entity in a spelling that appears nowhere in the text: "Ташкент" for posts
    -- that say "Toshkent". The tag alias table already holds those equivalences, so use it as a
    -- retrieval signal, not just as a browse filter.
    SELECT pt.post_id,
           row_number() OVER (ORDER BY max(word_similarity(:query_norm, ta.alias_norm)) DESC, count(*) DESC) AS rank
    FROM tag_aliases ta
    JOIN tags t ON t.id = ta.tag_id AND t.status = 'active'
    JOIN post_tags pt ON pt.tag_id = t.id
    JOIN filtered f ON f.id = pt.post_id
    WHERE ta.tenant_id = :tenant_id
      AND :query_norm <> ''
      AND word_similarity(:query_norm, ta.alias_norm) > 0.85
    GROUP BY pt.post_id
    LIMIT :pool
),
fused AS (
    SELECT post_id, sum(weight) AS score FROM (
        SELECT post_id, 1.0 / (:rrf_k + rank) AS weight FROM vec
        UNION ALL
        SELECT post_id, 1.0 / (:rrf_k + rank) FROM fts
        UNION ALL
        SELECT post_id, 0.5 / (:rrf_k + rank) FROM trgm
        UNION ALL
        SELECT post_id, 0.8 / (:rrf_k + rank) FROM alias_hits
    ) u GROUP BY post_id
)
SELECT p.id, f.score
FROM fused f JOIN posts p ON p.id = f.post_id
ORDER BY
    CASE WHEN :sort = 'relevance' THEN f.score END DESC NULLS LAST,
    CASE WHEN :sort = 'newest'    THEN p.date END DESC NULLS LAST,
    CASE WHEN :sort = 'oldest'    THEN p.date END ASC  NULLS LAST,
    CASE WHEN :sort = 'views'     THEN p.views END DESC NULLS LAST,
    CASE WHEN :sort = 'reactions' THEN p.reactions_total END DESC NULLS LAST,
    p.date DESC
LIMIT :limit OFFSET :offset
"""
)

# Filter-only browse (no query text): tags, dates, media kind.
BROWSE_SQL = text(
    """
SELECT p.id, CAST(0 AS float) AS score
FROM posts p
WHERE p.tenant_id = :tenant_id
  AND p.is_deleted = false
  AND p.is_album_root = true
  AND (CAST(:date_from AS timestamptz) IS NULL OR p.date >= :date_from)
  AND (CAST(:date_to AS timestamptz) IS NULL OR p.date <= :date_to)
  AND (CAST(:media_kind AS text) IS NULL OR p.media_kind = :media_kind)
  AND (:tag_count = 0 OR (
        SELECT count(DISTINCT t.id)
        FROM post_tags pt JOIN tags t ON t.id = pt.tag_id
        WHERE pt.post_id = p.id AND t.slug = ANY(:tag_slugs)
      ) = :tag_count)
ORDER BY
    CASE WHEN :sort = 'oldest'    THEN p.date END ASC  NULLS LAST,
    CASE WHEN :sort = 'views'     THEN p.views END DESC NULLS LAST,
    CASE WHEN :sort = 'reactions' THEN p.reactions_total END DESC NULLS LAST,
    p.date DESC
LIMIT :limit OFFSET :offset
"""
)


async def search(
    tenant_id: int,
    query: str | None = None,
    *,
    tag_slugs: list[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    media_kind: str | None = None,
    sort: Sort = "relevance",
    limit: int = 20,
    offset: int = 0,
) -> list[tuple[int, float]]:
    """Returns (post_id, score) ordered for display."""
    from kanalchi.text.normalize import normalize

    tags = tag_slugs or []
    params: dict[str, Any] = {
        "tenant_id": tenant_id,
        "tag_slugs": tags,
        "tag_count": len(tags),
        "date_from": date_from,
        "date_to": date_to,
        "media_kind": media_kind,
        "sort": sort,
        "limit": limit,
        "offset": offset,
    }
    if not (query or "").strip():
        params["sort"] = "newest" if sort == "relevance" else sort
        async with session_scope() as db:
            rows = (await db.execute(BROWSE_SQL, params)).all()
        return [(r[0], float(r[1])) for r in rows]

    # Semantic recall is an enhancement, not a dependency: if the embedding provider is unavailable
    # or unconfigured, the query still runs on full text + trigram instead of failing.
    qvec: str | None = None
    try:
        from kanalchi.ai.embeddings import embed_one

        qvec = str(await embed_one(query, input_type="query", tenant_id=tenant_id))
    except Exception as exc:  # noqa: BLE001
        log.warning("search.embedding_unavailable", error=str(exc)[:200])

    params |= {
        "query": query,
        "query_norm": normalize(query),
        "qvec": qvec,
        "pool": POOL,
        "rrf_k": RRF_K,
    }
    async with session_scope() as db:
        rows = (await db.execute(SEARCH_SQL, params)).all()
    return [(r[0], float(r[1])) for r in rows]


FACETS_SQL = text(
    """
SELECT d.key, t.slug, t.canonical_name, t.labels, count(*) AS cnt
FROM post_tags pt
JOIN tags t ON t.id = pt.tag_id AND t.status = 'active'
JOIN dimensions d ON d.id = t.dimension_id AND d.is_visible = true
WHERE pt.tenant_id = :tenant_id AND pt.post_id = ANY(:post_ids)
GROUP BY d.key, d.sort_order, t.slug, t.canonical_name, t.labels
ORDER BY d.sort_order, cnt DESC
"""
)


async def facets(
    tenant_id: int, post_ids: list[int], per_dimension: int = 12
) -> dict[str, list[dict[str, Any]]]:
    """Tag counts within a result set, for the search sidebar."""
    if not post_ids:
        return {}
    async with session_scope() as db:
        rows = (await db.execute(FACETS_SQL, {"tenant_id": tenant_id, "post_ids": post_ids})).all()
    out: dict[str, list[dict[str, Any]]] = {}
    for key, slug, name, labels, cnt in rows:
        bucket = out.setdefault(key, [])
        if len(bucket) < per_dimension:
            bucket.append({"slug": slug, "name": name, "labels": labels or {}, "count": cnt})
    return out


RELATED_SQL = text(
    """
SELECT c2.post_id, min(c1.embedding <=> c2.embedding) AS distance
FROM post_chunks c1
JOIN post_chunks c2
  ON c2.tenant_id = c1.tenant_id AND c2.post_id <> c1.post_id AND c2.embedding IS NOT NULL
JOIN posts p ON p.id = c2.post_id AND p.is_deleted = false AND p.is_album_root = true
WHERE c1.post_id = :post_id AND c1.tenant_id = :tenant_id AND c1.embedding IS NOT NULL
GROUP BY c2.post_id
ORDER BY distance
LIMIT :limit
"""
)


async def related(tenant_id: int, post_id: int, limit: int = 5) -> list[int]:
    async with session_scope() as db:
        rows = (
            await db.execute(RELATED_SQL, {"tenant_id": tenant_id, "post_id": post_id, "limit": limit})
        ).all()
    return [r[0] for r in rows]
