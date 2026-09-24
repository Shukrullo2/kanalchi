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


CURRENCY = "UZS"


def plan_catalogue() -> list[dict[str, Any]]:
    """The three plans with their monthly price in soums and what they switch on."""
    s = get_settings()
    return [
        {"id": "archive", "monthly_uzs": s.plan_archive_uzs, "live_updates": False, "writing_tools": False},
        {"id": "basic", "monthly_uzs": s.plan_basic_uzs, "live_updates": True, "writing_tools": False},
        {"id": "premium", "monthly_uzs": s.plan_premium_uzs, "live_updates": True, "writing_tools": True},
    ]


def plan_price_uzs(plan: str | None) -> int | None:
    for p in plan_catalogue():
        if p["id"] == plan:
            return int(p["monthly_uzs"])
    return None


def has_live_updates(tenant: Tenant) -> bool:
    """New posts keep flowing in. A channel with no plan chosen yet is one connected by the
    admin before plans existed, and keeps everything."""
    return tenant.plan is None or tenant.plan != "archive"


def has_writing_tools(tenant: Tenant) -> bool:
    """The studio's ideas, drafts, research and publishing."""
    return tenant.plan is None or tenant.plan == "premium"


def quote_for_posts(
    posts: int,
    *,
    source: str,
    avg_post_tokens: float | None = None,
    text_share: float | None = None,
) -> dict[str, Any]:
    """Price the import of an archive of `posts` messages.

    `source` records where the count came from: "telegram" (measured) or "manual" (typed in by
    the blogger), so a measured figure is never overwritten by a guess. The measured average
    post length and share of posts with text, when the preview job sampled them, bring the
    estimate within a few percent of what the first real channel cost.
    """
    from kanalchi.jobs.pipeline import DEFAULT_POST_TOKENS, DEFAULT_TEXT_SHARE, estimate_lines

    s = get_settings()
    posts = max(0, int(posts))
    lines = estimate_lines(
        posts,
        avg_tokens=avg_post_tokens or DEFAULT_POST_TOKENS,
        text_share=text_share if text_share is not None else DEFAULT_TEXT_SHARE,
    )
    ai_usd = round(sum(lines.values()), 2)
    price_uzs = int(round(ai_usd * s.onboarding_markup * s.usd_uzs_rate / 1000.0)) * 1000
    return {
        "posts": posts,
        "ai_usd": ai_usd,
        "price_uzs": price_uzs,
        "source": source,
        "avg_post_tokens": int(avg_post_tokens) if avg_post_tokens else None,
        "computed_at": datetime.now(UTC).isoformat(),
    }


def public_quote(quote: dict[str, Any] | None) -> dict[str, Any] | None:
    """The quote as the blogger sees it: the post count and the price, not how it was made."""
    if quote is None:
        return None
    return {k: quote[k] for k in ("posts", "price_uzs", "source", "computed_at") if k in quote}
