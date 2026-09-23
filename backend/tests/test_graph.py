"""The map endpoint: window bounds, the post cap, and links into the channel itself."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from kanalchi.api.routers.graph import own_post_ids
from kanalchi.core.db import session_scope
from kanalchi.core.models import Post, Tenant


def test_own_post_ids_parses_channel_links():
    urls = [
        "https://t.me/bakiroo/608",
        "http://t.me/bakiroo/609?single",
        "https://t.me/BAKIROO/610/",
        "https://t.me/other/611",
        "https://t.me/bakiroo",
        "https://t.me/c/123/5",
    ]
    assert own_post_ids(urls, "bakiroo") == [608, 609, 610]


def test_own_post_ids_without_username():
    assert own_post_ids(["https://t.me/bakiroo/608"], None) == []


async def _demo() -> tuple[str, int] | None:
    try:
        async with session_scope() as db:
            await db.execute(text("SELECT 1"))
            tenant = await db.scalar(select(Tenant).where(Tenant.domain == "demo.localhost"))
            if tenant is None:
                return None
            n = await db.scalar(select(Post.id).where(Post.tenant_id == tenant.id).limit(1))
            return (tenant.domain, tenant.id) if n else None
    except Exception:
        return None


@pytest.fixture(scope="session")
async def demo_host() -> str:
    demo = await _demo()
    if demo is None:
        pytest.skip("dev database with seeded demo tenant is not available")
    return demo[0]


@pytest.fixture
async def client():
    from httpx import ASGITransport, AsyncClient

    from kanalchi.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_graph_window_and_shape(client, demo_host: str):
    res = await client.get(
        "/api/graph?from=2000-01-01&to=2100-01-01&limit=50", headers={"x-tenant-host": demo_host}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["from"] == "2000-01-01" and body["to"] == "2100-01-01"
    assert body["posts"] and body["months"]
    ids = {p["id"] for p in body["posts"]}
    dates = [p["date"] for p in body["posts"]]
    assert dates == sorted(dates, reverse=True)
    for p in body["posts"]:
        # every edge points at a drawn post, every tag index at a listed tag
        assert p["reply"] is None or p["reply"] in ids
        assert all(link in ids for link in p["links"])
        assert all(0 <= i < len(body["tags"]) for i in p["tags"])
    assert all(t["dimension"] not in {"link_domains", "language", "media_type"} for t in body["tags"])
    counts = [t["count"] for t in body["tags"]]
    assert counts == sorted(counts, reverse=True)


@pytest.mark.asyncio
async def test_graph_cap_marks_truncation(client, demo_host: str):
    res = await client.get(
        "/api/graph?from=2000-01-01&to=2100-01-01&limit=50", headers={"x-tenant-host": demo_host}
    )
    body = res.json()
    async with session_scope() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.domain == demo_host))
        total = len(
            (
                await db.scalars(
                    select(Post.id).where(
                        Post.tenant_id == tenant.id, Post.is_deleted.is_(False), Post.is_album_root.is_(True)
                    )
                )
            ).all()
        )
    assert body["truncated"] == (total > 50)
    assert len(body["posts"]) == min(total, 50)


@pytest.mark.asyncio
async def test_graph_empty_window(client, demo_host: str):
    res = await client.get("/api/graph?from=1990-01-01&to=1990-01-02", headers={"x-tenant-host": demo_host})
    assert res.status_code == 200
    assert res.json()["posts"] == []
