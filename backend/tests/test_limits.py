"""Rate limits and budgets. These run against the dev Redis and skip when it is unavailable."""

from __future__ import annotations

import uuid

import pytest

from kanalchi.core.limits import BudgetState, add_spend, check_chat_rate, get_budget, ip_hash
from kanalchi.core.redis import get_redis
from kanalchi.core.settings import get_settings


async def _redis_available() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


@pytest.fixture(autouse=True)
async def _require_redis():
    if not await _redis_available():
        pytest.skip("redis is not available")


def test_ip_hash_is_stable_and_not_reversible():
    a, b = ip_hash("203.0.113.7"), ip_hash("203.0.113.7")
    assert a == b
    assert "203.0.113.7" not in a
    assert a != ip_hash("203.0.113.8")


def test_ip_hash_handles_missing_address():
    assert ip_hash(None)


async def test_rate_limit_allows_then_blocks():
    s = get_settings()
    tenant = 900_000 + abs(hash(uuid.uuid4())) % 1000
    ip = f"198.51.100.{tenant % 250}"
    allowed = 0
    for _ in range(s.viewer_chat_per_ip_10min + 2):
        result = await check_chat_rate(tenant, ip=ip, visitor_id=f"v{tenant}")
        if result.allowed:
            allowed += 1
        else:
            assert result.reason == "rate_limited"
            assert result.retry_after_s and result.retry_after_s > 0
            break
    assert allowed == s.viewer_chat_per_ip_10min


async def test_separate_visitors_have_separate_budgets():
    tenant = 910_000 + abs(hash(uuid.uuid4())) % 1000
    first = await check_chat_rate(tenant, ip="198.51.100.1", visitor_id="a")
    second = await check_chat_rate(tenant, ip="198.51.100.2", visitor_id="b")
    assert first.allowed and second.allowed


async def test_spend_accumulates_within_the_day():
    tenant = 920_000 + abs(hash(uuid.uuid4())) % 1000
    await add_spend(tenant, "chat", 0.25)
    await add_spend(tenant, "chat", 0.25)
    state = await get_budget(tenant, "chat", 5.0)
    assert state.spent_usd == pytest.approx(0.5)
    assert not state.exhausted


async def test_budget_blocks_once_the_cap_is_reached():
    tenant = 930_000 + abs(hash(uuid.uuid4())) % 1000
    await add_spend(tenant, "chat", 5.0)
    state = await get_budget(tenant, "chat", 5.0)
    assert state.exhausted
    assert state.remaining_usd == 0


def test_budget_warning_threshold():
    assert BudgetState(spent_usd=4.0, limit_usd=5.0).warning
    assert not BudgetState(spent_usd=3.0, limit_usd=5.0).warning
    assert not BudgetState(spent_usd=100.0, limit_usd=0.0).exhausted  # 0 means "no cap"
