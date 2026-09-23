"""The reconciler, the estimate and domain-less onboarding, against the dev Postgres.

These exercise real queries rather than mocks: a stage count that compiles but selects the
wrong column would pass any unit test and mislead every operator. Writes happen inside a
transaction that is rolled back, so the seeded database is left as it was.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from kanalchi.core.db import get_sessionmaker, session_scope
from kanalchi.core.models import Tenant

pytestmark = pytest.mark.asyncio


async def _bakiroo_id() -> int | None:
    try:
        async with session_scope() as db:
            await db.execute(text("SELECT 1"))
            return await db.scalar(select(Tenant.id).where(Tenant.slug == "the-bakiroo"))
    except Exception:
        return None


@pytest.fixture
async def tenant_id() -> int:
    found = await _bakiroo_id()
    if found is None:
        pytest.skip("dev Postgres with the bakiroo tenant is not reachable")
    return found


async def test_status_reports_every_stage(tenant_id: int):
    from kanalchi.jobs.pipeline import STAGES, pipeline_status

    status = await pipeline_status(tenant_id)
    assert set(status["stages"]) == set(STAGES)
    assert status["stage"] in {*STAGES, "done"}
    imp = status["stages"]["import"]
    assert imp["imported"] > 0 and imp["total"] and imp["imported"] <= imp["total"] + 100
    ext = status["stages"]["extract"]
    assert ext["succeeded"] + ext["pending"] + ext["in_flight"] + ext["failed"] == ext["total"]
    emb = status["stages"]["embed"]
    assert emb["embedded"] + emb["pending"] + emb["skipped"] == emb["total"]
    assert set(status["workers"]) == {"telegram", "index"}


async def test_estimate_is_measured_from_the_channel(tenant_id: int):
    from kanalchi.jobs.pipeline import estimate

    est = await estimate(tenant_id)
    assert est["measured_from_channel"] is True
    assert est["posts_total"] >= est["posts_imported"] > 0
    assert est["total_usd"] == round(sum(est["lines"].values()), 2)
    assert est["lines"]["taxonomy"] == 0.0, "an applied index should not be quoted again"


async def test_reconcile_queues_nothing_without_keys(tenant_id: int, monkeypatch: pytest.MonkeyPatch):
    from kanalchi.core.settings import get_settings
    from kanalchi.jobs.pipeline import reconcile

    # Without keys every AI step is skipped, so nothing is deferred and the queue is not touched.
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    monkeypatch.setattr(get_settings(), "voyage_api_key", None)
    actions = await reconcile(tenant_id)
    assert not any(a.endswith(": queued") for a in actions), actions


async def test_tenant_without_domain_lives_under_the_platform_domain(tenant_id: int):
    from kanalchi.api.routers.admin import TenantCreate, create_tenant
    from kanalchi.core.members import list_members
    from kanalchi.core.settings import get_settings

    async with get_sessionmaker()() as db:
        try:
            out = await create_tenant(
                TenantCreate(title="Rollback test", owner_tg_id=987654321, owner_name="Tester"), db
            )
            assert out["domain"].endswith("." + get_settings().tenant_base_domain)
            assert out["auto_domain"] is True
            assert out["domain_verified_at"] is not None, "the platform wildcard needs no DNS check"
            members = await list_members(db, out["id"])
            assert [(m["tg_user_id"], m["role"], m["invited"]) for m in members] == [
                (987654321, "owner", True)
            ]
        finally:
            await db.rollback()
