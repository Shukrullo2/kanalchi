"""The pending-tag upsert, exercised against a real Postgres.

This one has to execute, not merely compile. The bug it guards against was a
statement that compiled perfectly and that the server then refused: an array
slice whose bounds came out as bind parameters, which Postgres rejects. A
compile-only assertion passed happily while every one of 5,000 extractions
failed to store, so the test runs the statement or it is worth nothing.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select, text

from kanalchi.ai.mapping import record_candidate
from kanalchi.core.db import session_scope
from kanalchi.core.models import Dimension, TagCandidate, Tenant

pytestmark = pytest.mark.asyncio

TENANT_DOMAIN = "demo.localhost"


async def _fixture_ids() -> tuple[int, int] | None:
    """(tenant_id, dimension_id) from the seeded dev database, or None if it is not up."""
    try:
        async with session_scope() as db:
            await db.execute(text("SELECT 1"))
            tenant = await db.scalar(select(Tenant).where(Tenant.domain == TENANT_DOMAIN))
            if tenant is None:
                return None
            dimension = await db.scalar(
                select(Dimension).where(Dimension.tenant_id == tenant.id, Dimension.key == "people")
            )
            return (tenant.id, dimension.id) if dimension else None
    except Exception:
        return None


@pytest.fixture
async def ids() -> tuple[int, int]:
    found = await _fixture_ids()
    if found is None:
        pytest.skip("dev Postgres with a seeded demo tenant is not reachable")
    return found


async def test_repeat_sightings_accumulate_without_unbounded_growth(ids: tuple[int, int]):
    tenant_id, dimension_id = ids
    name = "Upsert Test Subject"
    async with session_scope() as db:
        await db.execute(
            delete(TagCandidate).where(TagCandidate.tenant_id == tenant_id, TagCandidate.name == name)
        )

    # Twelve sightings, past both the five-sample and eight-surface ceilings.
    async with session_scope() as db:
        for i in range(1, 13):
            await record_candidate(
                db, tenant_id, dimension_id, name, surface=f"form {i}", lang="uz", post_id=i
            )
            await db.flush()

    async with session_scope() as db:
        row = await db.scalar(
            select(TagCandidate).where(TagCandidate.tenant_id == tenant_id, TagCandidate.name == name)
        )
        assert row is not None, "the conflict path never stored anything"
        assert row.count == 12
        assert row.sample_post_ids == [1, 2, 3, 4, 5], "sample ids should stop at five"
        assert len(row.surface_forms) == 8, "surface forms should stop at eight"
        assert row.surface_forms[0] == "form 1"
        await db.execute(
            delete(TagCandidate).where(TagCandidate.tenant_id == tenant_id, TagCandidate.name == name)
        )
