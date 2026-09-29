"""Pricing a channel on the platform domain, open to anyone: type a channel's username, see what
importing it costs, then message the admin. Nothing is reserved by asking: no tenant, no slug,
no domain. The admin creates the tenant when the channel is actually onboarded."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from kanalchi.api.deps import enforce_same_origin, get_db
from kanalchi.core import billing
from kanalchi.core.limits import check_quote_rate, reader_quote_allowed
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, ChannelQuote, Tenant
from kanalchi.text.slug import slugify

log = get_logger(__name__)

router = APIRouter(prefix="/api/signup", tags=["signup"])

# @name, t.me/name, https://telegram.me/name/ — a public channel username, nothing else.
_USERNAME = re.compile(
    r"^(?:https?://)?(?:(?:www\.)?(?:t|telegram)\.me/(?:s/)?|@)?([A-Za-z][A-Za-z0-9_]{3,31})/?$"
)

# A measured quote is reused this long before Telegram is asked again.
QUOTE_FRESH = timedelta(days=7)
# The reader account answers within seconds unless its queue is busy; past this, the page stops
# waiting and shows what it has (the web estimate) or offers a retry.
MEASURE_PATIENCE = timedelta(minutes=3)
# Tenant states in which a channel is really on the platform (onboarding is still just a draft).
ONBOARDED = ("backfilling", "indexing", "active", "paused", "error")


def parse_channel_username(link: str) -> str | None:
    """The username in a channel link, or None for anything that is not a public channel link."""
    link = link.strip()
    if "joinchat" in link or "/+" in link or link.startswith("+"):
        return None
    m = _USERNAME.match(link)
    return m.group(1).lower() if m else None


@router.get("/plans")
async def plans() -> dict:
    """Public: what the landing page says about money. The import is priced per channel; hosting
    is free for the first month, and the plans are agreed with the admin after that."""
    return {
        "currency": billing.CURRENCY,
        "plans": billing.plan_catalogue(),
        "first_month_free": True,
        "onboarding": {"sample": billing.public_quote(billing.quote_for_posts(1000, source="sample"))},
    }


class QuoteIn(BaseModel):
    link: str = Field(min_length=4, max_length=200)


def _quote_out(row: ChannelQuote, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    state = row.status
    if state == "pending" and now - row.updated_at > MEASURE_PATIENCE:
        # The measuring job never answered (worker down, queue busy): do not spin forever.
        state = "done" if row.quote else "failed"
    return {
        "username": row.username,
        "title": row.title,
        "participants_count": row.participants_count,
        # pending: Telegram is measuring it (a web estimate may already be in `quote`);
        # done: final; failed: nothing could be measured, the page offers a retry.
        "status": state,
        "quote": billing.public_quote(row.quote),
    }


async def _onboarded(db: AsyncSession, username: str) -> Tenant | None:
    return await db.scalar(
        select(Tenant)
        .outerjoin(Channel, Channel.tenant_id == Tenant.id)
        .where(
            or_(Tenant.slug == slugify(username), Channel.username.ilike(username)),
            Tenant.status.in_(ONBOARDED),
        )
        .limit(1)
    )


async def _web_estimate(row: ChannelQuote) -> bool:
    """Price the channel from its t.me/s page, right now. False when it has no web preview."""
    from kanalchi.jobs.pipeline import CHARS_PER_TOKEN
    from kanalchi.telegram.webpreview import fetch_web_preview

    web = await fetch_web_preview(row.username)
    if web is None:
        return False
    row.title = web["title"] or row.title
    row.participants_count = web["participants_count"] or row.participants_count
    # Never replace a figure Telegram itself measured with the rougher web one.
    if (row.quote or {}).get("source") != "telegram":
        avg = web["avg_chars"]
        row.quote = billing.quote_for_posts(
            web["total"],
            source="web",
            avg_post_tokens=avg / CHARS_PER_TOKEN if avg else None,
            text_share=web["text_share"],
        )
    return True


@router.post("/quote", dependencies=[Depends(enforce_same_origin)])
async def quote_channel(
    body: QuoteIn, request: Request, background: BackgroundTasks, db: AsyncSession = Depends(get_db)
) -> dict:
    """Price a public channel. Asking again for a channel whose quote failed or went stale starts
    over, which is also what the page's retry button does."""
    username = parse_channel_username(body.link)
    if username is None:
        raise HTTPException(400, "send a public channel link or @username (private channels: contact us)")
    tenant = await _onboarded(db, username)
    if tenant is not None:
        raise HTTPException(409, "this channel is already on the platform")
    limit = await check_quote_rate(request.client.host if request.client else None)
    if not limit.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many channels priced in a short time, try again later",
            headers={"Retry-After": str(limit.retry_after_s or 3600)},
        )

    now = datetime.now(UTC)
    row = await db.scalar(select(ChannelQuote).where(ChannelQuote.username == username))
    if row is not None:
        out = _quote_out(row, now=now)
        fresh = (
            row.quote
            and row.quote.get("source") == "telegram"
            and (now - datetime.fromisoformat(row.quote["computed_at"]) < QUOTE_FRESH)
        )
        if fresh or out["status"] == "pending":
            row.times_asked += 1
            background.add_task(_notify, _report(row, f"Priced again ({row.times_asked}×)"))
            return out

    first = row is None
    if row is None:
        row = ChannelQuote(username=username, times_asked=1)
        db.add(row)
    else:
        row.times_asked += 1
    row.status, row.error = "pending", None
    row.updated_at = now
    has_web = await _web_estimate(row)
    # Committed before the job is queued: the worker picks it up at once and must find the row.
    await db.commit()

    deferred = False
    if await reader_quote_allowed():
        try:
            from kanalchi.jobs import telegram_jobs

            await telegram_jobs.channel_quote.defer_async(username=username)
            deferred = True
        except Exception as exc:  # noqa: BLE001
            log.warning("signup.quote.defer_failed", username=username, error=str(exc)[:200])
    if not deferred:
        row.status = "done" if row.quote else "failed"
        row.error = None if row.quote else "the reader account is not available"
    if not has_web and not deferred:
        row.error = "no public web preview and the reader account is not available"

    background.add_task(
        _notify, _report(row, "New channel priced" if first else f"Priced again ({row.times_asked}×)")
    )
    log.info("signup.quote", username=username, status=row.status, web=has_web, deferred=deferred)
    return _quote_out(row, now=now)


@router.get("/quote/{username}")
async def get_quote(username: str, db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.scalar(select(ChannelQuote).where(ChannelQuote.username == username.lower()))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "this channel has not been priced")
    return _quote_out(row)


def _report(row: ChannelQuote, note: str) -> str:
    """Every ask is reported (the visitor is anonymous; the channel is the lead to contact)."""
    return (
        billing.quote_report(row.username, row.title, row.participants_count, row.quote, note)
        + (
            "\n(Telegram is still measuring; a follow-up comes if the price changes)"
            if row.status == "pending"
            else ""
        )
        + (f"\n⚠️ {row.error}" if row.error else "")
    )


async def _notify(message: str) -> None:
    """Tell the admins on Telegram; a failure here must never fail the quote."""
    try:
        from kanalchi.jobs.periodic import _alert_admins

        await _alert_admins(message)
    except Exception as exc:  # noqa: BLE001
        log.warning("signup.notify_failed", error=str(exc)[:200])
