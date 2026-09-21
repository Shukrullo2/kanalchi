"""Rate limits and spend budgets, enforced in Redis before any model call.

Viewer chat is open to anyone, so the protection has to sit in front of the expensive part: a
sliding-window counter per IP and per visitor, and a hard daily dollar cap per tenant that is
checked before the turn starts and incremented from measured usage after it ends.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from kanalchi.core.logging import get_logger
from kanalchi.core.redis import get_redis
from kanalchi.core.settings import get_settings

log = get_logger(__name__)

# Sliding window: drop entries older than the window, count what is left, add this one.
_SLIDING_WINDOW = """
local key, now, window, limit = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local used = redis.call('ZCARD', key)
if used >= limit then
  return {0, used}
end
redis.call('ZADD', key, now, ARGV[4])
redis.call('EXPIRE', key, window)
return {1, used + 1}
"""


def ip_hash(ip: str | None) -> str:
    salt = get_settings().session_secret
    return hashlib.sha256(f"{salt}:{ip or 'unknown'}".encode()).hexdigest()[:32]


@dataclass(slots=True)
class LimitResult:
    allowed: bool
    reason: str | None = None
    retry_after_s: int | None = None
    used: int = 0
    limit: int = 0


async def _sliding(key: str, window_s: int, limit: int) -> LimitResult:
    r = get_redis()
    now = datetime.now(UTC).timestamp()
    member = f"{now:.6f}"
    try:
        ok, used = await r.eval(_SLIDING_WINDOW, 1, key, str(now), str(window_s), str(limit), member)
    except Exception as exc:  # noqa: BLE001
        # Redis being down must not take the site down; log loudly and let the request through.
        log.warning("limits.redis_unavailable", key=key, error=str(exc)[:200])
        return LimitResult(True)
    if not ok:
        return LimitResult(False, reason="rate_limited", retry_after_s=window_s, used=int(used), limit=limit)
    return LimitResult(True, used=int(used), limit=limit)


async def check_chat_rate(tenant_id: int, *, ip: str | None, visitor_id: str | None) -> LimitResult:
    s = get_settings()
    checks = [
        (f"rl:chat:{tenant_id}:ip:{ip_hash(ip)}:10m", 600, s.viewer_chat_per_ip_10min),
        (f"rl:chat:{tenant_id}:day:{visitor_id or ip_hash(ip)}", 86400, s.viewer_chat_per_visitor_day),
        (f"rl:chat:{tenant_id}:tenant:day", 86400, s.viewer_chat_per_tenant_day),
    ]
    for key, window, limit in checks:
        result = await _sliding(key, window, limit)
        if not result.allowed:
            return result
    return LimitResult(True)


def _budget_key(tenant_id: int, kind: str) -> str:
    return f"budget:{tenant_id}:{kind}:{datetime.now(UTC):%Y-%m-%d}"


@dataclass(slots=True)
class BudgetState:
    spent_usd: float
    limit_usd: float

    @property
    def exhausted(self) -> bool:
        return self.limit_usd > 0 and self.spent_usd >= self.limit_usd

    @property
    def warning(self) -> bool:
        return self.limit_usd > 0 and self.spent_usd >= self.limit_usd * 0.8

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.limit_usd - self.spent_usd)


async def get_budget(tenant_id: int, kind: str, limit_usd: float) -> BudgetState:
    try:
        raw = await get_redis().get(_budget_key(tenant_id, kind))
    except Exception as exc:  # noqa: BLE001
        log.warning("limits.budget_unavailable", error=str(exc)[:200])
        return BudgetState(0.0, limit_usd)
    return BudgetState(float(raw or 0.0), limit_usd)


async def add_spend(tenant_id: int, kind: str, usd: float) -> float:
    """Increment today's counter. Kept in Redis for speed; `usage_ledger` is the durable record."""
    if usd <= 0:
        return 0.0
    key = _budget_key(tenant_id, kind)
    try:
        r = get_redis()
        total = await r.incrbyfloat(key, usd)
        await r.expire(key, 172800)
        return float(total)
    except Exception as exc:  # noqa: BLE001
        log.warning("limits.spend_not_recorded", error=str(exc)[:200])
        return 0.0


async def check_platform_cap() -> bool:
    """Global kill switch so one runaway tenant cannot spend the whole month's budget."""
    s = get_settings()
    if s.platform_daily_llm_cap_usd <= 0:
        return True
    try:
        raw = await get_redis().get(f"budget:platform:{datetime.now(UTC):%Y-%m-%d}")
    except Exception:  # noqa: BLE001
        return True
    return float(raw or 0.0) < s.platform_daily_llm_cap_usd


async def add_platform_spend(usd: float) -> None:
    if usd <= 0:
        return
    try:
        r = get_redis()
        key = f"budget:platform:{datetime.now(UTC):%Y-%m-%d}"
        await r.incrbyfloat(key, usd)
        await r.expire(key, 172800)
    except Exception:  # noqa: BLE001
        pass
