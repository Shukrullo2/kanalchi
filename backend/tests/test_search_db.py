"""Search behaviour against the real database.

These run against the local dev Postgres seeded by `kanalchi seed-dev --posts 24 && kanalchi seed-tags`
and are skipped when it is not reachable. They cover the property the whole product depends on:
a reader can find a post in a language or script the post was not written in.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from kanalchi.core.db import session_scope
from kanalchi.core.models import Post, Tenant
from kanalchi.search import hybrid

pytestmark = pytest.mark.asyncio


async def _tenant_id() -> int | None:
    try:
        async with session_scope() as db:
            await db.execute(text("SELECT 1"))
            tenant = await db.scalar(select(Tenant).where(Tenant.domain == "demo.localhost"))
            if tenant is None:
                return None
            posts = await db.scalar(select(Post.id).where(Post.tenant_id == tenant.id).limit(1))
            return tenant.id if posts else None
    except Exception:
        return None


@pytest.fixture(scope="module")
async def tenant_id() -> int:
    tid = await _tenant_id()
    if tid is None:
        pytest.skip("dev database with seeded demo tenant is not available")
    return tid


async def test_browse_without_query_returns_newest_first(tenant_id: int):
    rows = await hybrid.search(tenant_id, None, limit=5)
    assert len(rows) == 5
    async with session_scope() as db:
        dates = [await db.scalar(select(Post.date).where(Post.id == pid)) for pid, _ in rows]
    assert dates == sorted(dates, reverse=True)


async def test_sort_by_views(tenant_id: int):
    rows = await hybrid.search(tenant_id, None, sort="views", limit=5)
    async with session_scope() as db:
        views = [await db.scalar(select(Post.views).where(Post.id == pid)) for pid, _ in rows]
    assert views == sorted(views, reverse=True)


async def test_latin_query_matches_latin_post(tenant_id: int):
    rows = await hybrid.search(tenant_id, "hokimligi", limit=5)
    assert rows, "expected the Latin query to match"


async def test_uzbek_cyrillic_query_matches_latin_post(tenant_id: int):
    """Тошкент and Toshkent are the same place; normalization must make them collide."""
    rows = await hybrid.search(tenant_id, "Тошкент", limit=5)
    assert rows, "Cyrillic query found nothing"


async def test_russian_spelling_matches_via_tag_alias(tenant_id: int):
    """Ташкент shares no substring with Toshkent, so only the alias table can bridge it."""
    rows = await hybrid.search(tenant_id, "Ташкент", limit=5)
    assert rows, "Russian spelling found nothing"


async def test_russian_abbreviation_matches_via_tag_alias(tenant_id: int):
    rows = await hybrid.search(tenant_id, "Минюст", limit=5)
    assert rows, "Russian abbreviation found nothing"


async def test_typo_is_tolerated(tenant_id: int):
    rows = await hybrid.search(tenant_id, "hokimlgi", limit=5)
    assert rows, "expected trigram matching to absorb the typo"


async def test_nonsense_query_returns_nothing(tenant_id: int):
    assert await hybrid.search(tenant_id, "zzzzqqqqxxxx", limit=5) == []


async def test_tag_filter_narrows_results(tenant_id: int):
    all_rows = await hybrid.search(tenant_id, None, limit=50)
    tagged = await hybrid.search(tenant_id, None, tag_slugs=["toshkent"], limit=50)
    assert 0 < len(tagged) < len(all_rows)


async def test_unknown_tag_filter_returns_nothing(tenant_id: int):
    assert await hybrid.search(tenant_id, None, tag_slugs=["no-such-tag"], limit=10) == []


async def test_facets_group_by_dimension(tenant_id: int):
    rows = await hybrid.search(tenant_id, None, limit=10)
    facets = await hybrid.facets(tenant_id, [pid for pid, _ in rows])
    assert "locations" in facets or "themes" in facets
    for _dimension, tags in facets.items():
        assert all(t["count"] > 0 for t in tags)


async def test_pagination_does_not_repeat(tenant_id: int):
    first = await hybrid.search(tenant_id, None, limit=5, offset=0)
    second = await hybrid.search(tenant_id, None, limit=5, offset=5)
    assert not ({p for p, _ in first} & {p for p, _ in second})
