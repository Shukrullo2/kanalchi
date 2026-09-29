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
        ("https://t.me/s/the_bakiroo", "the_bakiroo"),  # the web preview link
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


def test_quote_is_the_ai_cost_plus_a_margin_in_whole_thousands_of_soums() -> None:
    s = get_settings()
    small = billing.quote_for_posts(10, source="manual")
    large = billing.quote_for_posts(20_000, source="telegram", avg_post_tokens=320, text_share=0.95)
    assert large["price_uzs"] > small["price_uzs"] > 0
    assert large["price_uzs"] % 1000 == 0
    # A tiny archive still carries the minimum margin; a big one carries the share.
    assert small["margin_uzs"] == s.onboarding_margin_min_uzs
    assert abs(large["margin_uzs"] - large["ai_usd"] * s.usd_uzs_rate * s.onboarding_margin_share) < 2
    expected = large["ai_usd"] * s.usd_uzs_rate + large["margin_uzs"]
    assert 0 <= large["price_uzs"] - expected < 1000
    # The margin is a floor: whatever the AI cost, the price is at least that much above it.
    for posts in (1, 7, 50, 333, 4_000):
        q = billing.quote_for_posts(posts, source="manual")
        assert q["price_uzs"] - q["ai_usd"] * s.usd_uzs_rate >= s.onboarding_margin_min_uzs
    assert large["source"] == "telegram" and large["posts"] == 20_000
    # The blogger sees the price, never the margin or the dollar cost behind it.
    assert set(billing.public_quote(large)) == {"posts", "price_uzs", "source", "computed_at"}


def test_measured_length_changes_the_quote() -> None:
    short = billing.quote_for_posts(5_000, source="telegram", avg_post_tokens=120)
    long = billing.quote_for_posts(5_000, source="telegram", avg_post_tokens=600)
    assert long["ai_usd"] > short["ai_usd"]


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
    prices = [p["monthly_uzs"] for p in plans]
    assert prices == sorted(prices) == [90_000, 120_000, 150_000]
    assert billing.plan_price_uzs("basic") == prices[1]
    assert billing.plan_price_uzs(None) is None


_PAGE = """
<meta property="og:title" content="bakiroo &amp; co">
<div class="tgme_channel_info_counter"><span class="counter_value">60.3K</span> <span class="counter_type">subscribers</span></div>
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="the_bakiroo/13392">
  <div class="tgme_widget_message_text js-message_text" dir="auto">Hello <b>world</b><br/>again &amp; more</div>
</div>
<div class="tgme_widget_message js-widget_message" data-post="the_bakiroo/13393">
  <a class="tgme_widget_message_photo_wrap"></a>
</div>
<div class="tgme_widget_message js-widget_message" data-post="the_bakiroo/13394">
  <div class="tgme_widget_message_reply"><div class="tgme_widget_message_metatext js-message_reply_text">quoted</div></div>
  <div class="tgme_widget_message_text js-message_text" dir="auto">abc</div>
</div>
"""


def test_web_preview_page_gives_ids_text_lengths_and_header() -> None:
    from kanalchi.telegram.webpreview import parse_count, parse_page

    page = parse_page(_PAGE)
    assert page["posts"] == {13392: len("Hello world\nagain & more"), 13393: 0, 13394: 3}
    assert page["title"] == "bakiroo & co"
    assert page["participants_count"] == 60_300
    assert parse_count("1.2M") == 1_200_000 and parse_count("812") == 812 and parse_count("?") is None


def test_a_quote_nobody_answers_stops_spinning() -> None:
    from datetime import UTC, datetime, timedelta

    from kanalchi.api.routers.signup import MEASURE_PATIENCE, _quote_out
    from kanalchi.core.models import ChannelQuote

    now = datetime.now(UTC)
    row = ChannelQuote(username="abcd", title="", status="pending", quote=None, updated_at=now)
    assert _quote_out(row, now=now)["status"] == "pending"
    late = now + MEASURE_PATIENCE + timedelta(seconds=1)
    # Nothing measured at all: the page offers a retry.
    assert _quote_out(row, now=late)["status"] == "failed"
    # A web estimate is there: it becomes the answer.
    row.quote = billing.quote_for_posts(500, source="web")
    out = _quote_out(row, now=late)
    assert out["status"] == "done" and out["quote"]["source"] == "web"
    assert "ai_usd" not in out["quote"]
