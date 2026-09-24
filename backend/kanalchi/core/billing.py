"""Plans, what each one unlocks, and the one-off onboarding quote.

Money is handled by hand for now: the admin agrees the price with the blogger on Telegram and
marks the tenant paid. This module only decides the numbers and the entitlements.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from kanalchi.core.settings import get_settings

if TYPE_CHECKING:
    from kanalchi.core.models import Tenant

PLANS = ("archive", "basic", "premium")
SUBSCRIPTION_STATUSES = ("none", "pending", "active", "past_due", "cancelled")


def plan_catalogue() -> list[dict[str, Any]]:
    """The three plans with their monthly price and what they switch on."""
    s = get_settings()
    return [
        {"id": "archive", "monthly_usd": s.plan_archive_usd, "live_updates": False, "writing_tools": False},
        {"id": "basic", "monthly_usd": s.plan_basic_usd, "live_updates": True, "writing_tools": False},
        {"id": "premium", "monthly_usd": s.plan_premium_usd, "live_updates": True, "writing_tools": True},
    ]


def plan_price_usd(plan: str | None) -> float | None:
    for p in plan_catalogue():
        if p["id"] == plan:
            return float(p["monthly_usd"])
    return None


def has_live_updates(tenant: Tenant) -> bool:
    """New posts keep flowing in. A channel with no plan chosen yet is one connected by the
    admin before plans existed, and keeps everything."""
    return tenant.plan is None or tenant.plan != "archive"


def has_writing_tools(tenant: Tenant) -> bool:
    """The studio's ideas, drafts, research and publishing."""
    return tenant.plan is None or tenant.plan == "premium"


def quote_for_posts(posts: int, *, source: str, avg_post_tokens: int | None = None) -> dict[str, Any]:
    """Price the import of an archive of `posts` messages.

    `source` records where the count came from: "telegram" (measured) or "manual" (typed in by
    the blogger), so a measured figure is never overwritten by a guess.
    """
    from kanalchi.jobs.pipeline import DEFAULT_POST_TOKENS, estimate_lines

    s = get_settings()
    posts = max(0, int(posts))
    lines = estimate_lines(posts, avg_tokens=avg_post_tokens or DEFAULT_POST_TOKENS)
    ai_usd = round(sum(lines.values()), 2)
    price = s.onboarding_base_usd + ai_usd * s.onboarding_ai_markup
    price = max(s.onboarding_min_usd, round(price))
    return {
        "posts": posts,
        "ai_usd": ai_usd,
        "price_usd": float(price),
        "source": source,
        "computed_at": datetime.now(UTC).isoformat(),
    }
