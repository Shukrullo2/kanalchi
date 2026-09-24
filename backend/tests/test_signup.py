"""Sign-up funnel: link parsing, plan entitlements and the onboarding quote (no database)."""

from __future__ import annotations

import pytest

from kanalchi.api.routers.signup import parse_channel_username
from kanalchi.core import billing
from kanalchi.core.models import Tenant
from kanalchi.core.settings import get_settings


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("@the_bakiroo", "the_bakiroo"),
        ("https://t.me/The_Bakiroo/", "the_bakiroo"),
        ("t.me/abc_1", "abc_1"),
        ("telegram.me/abc_1", "abc_1"),
        ("abc_1", "abc_1"),
        ("https://t.me/+abcdef", None),  # private invite
        ("https://t.me/joinchat/abcdef", None),
        ("ab", None),  # too short for a username
        ("the bakiroo", None),
        ("https://t.me/the_bakiroo/123", None),  # a post, not a channel
    ],
)
def test_parse_channel_username(link: str, expected: str | None) -> None:
    assert parse_channel_username(link) == expected


def test_quote_scales_with_posts_and_never_drops_below_the_floor() -> None:
    s = get_settings()
    small = billing.quote_for_posts(10, source="manual")
    large = billing.quote_for_posts(20_000, source="telegram")
    assert small["price_usd"] == s.onboarding_min_usd
    assert large["price_usd"] > small["price_usd"]
    assert large["price_usd"] >= s.onboarding_base_usd + large["ai_usd"] * s.onboarding_ai_markup - 1
    assert large["source"] == "telegram" and large["posts"] == 20_000


def test_plan_entitlements() -> None:
    archive, basic, premium, legacy = (Tenant(plan=p) for p in ("archive", "basic", "premium", None))
    assert not billing.has_live_updates(archive)
    assert billing.has_live_updates(basic) and billing.has_live_updates(premium)
    assert not billing.has_writing_tools(archive) and not billing.has_writing_tools(basic)
    assert billing.has_writing_tools(premium)
    # A channel connected before plans existed keeps everything.
    assert billing.has_live_updates(legacy) and billing.has_writing_tools(legacy)


def test_catalogue_lists_three_plans_in_ascending_price() -> None:
    plans = billing.plan_catalogue()
    assert [p["id"] for p in plans] == ["archive", "basic", "premium"]
    prices = [p["monthly_usd"] for p in plans]
    assert prices == sorted(prices)
    assert billing.plan_price_usd("basic") == prices[1]
    assert billing.plan_price_usd(None) is None
