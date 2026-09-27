"""Stage the local database for the fake registration in the demo, and put it back."""
import asyncio, json, sys
from sqlalchemy import select, delete
from kanalchi.core.db import session_scope
from kanalchi.core.models import Tenant, Channel
from kanalchi.core.billing import quote_for_posts

HOLD = "the-bakiroo-hold"

async def hold():
    async with session_scope() as db:
        t = await db.get(Tenant, 3)
        if t.slug == "the-bakiroo":
            t.slug = HOLD
        print("held", t.slug)

async def quote():
    async with session_scope() as db:
        t = await db.scalar(select(Tenant).where(Tenant.slug == "the-bakiroo", Tenant.source == "self"))
        real = await db.scalar(select(Channel).where(Channel.tenant_id == 3))
        q = quote_for_posts(12965, source="telegram", avg_post_tokens=321, text_share=0.947)
        t.onboarding_quote = q
        t.title = "bakiroo"
        t.settings = {**t.settings, "signup": {**t.settings["signup"], "preview": "done"}}
        if await db.scalar(select(Channel).where(Channel.tenant_id == t.id)) is None:
            db.add(Channel(tenant_id=t.id, tg_channel_id=9_999_000_001, username="the_bakiroo", title="bakiroo",
                           participants_count=real.participants_count, backfill_total_estimate=12965))
        print(t.id, q["price_uzs"])

async def cleanup():
    async with session_scope() as db:
        fake = await db.scalar(select(Tenant).where(Tenant.slug == "the-bakiroo", Tenant.source == "self"))
        if fake is not None:
            await db.execute(delete(Channel).where(Channel.tenant_id == fake.id))
            await db.delete(fake)
            print("deleted fake tenant", fake.id)
        t = await db.get(Tenant, 3)
        if t.slug == HOLD:
            t.slug = "the-bakiroo"
        print("restored", t.slug)

async def flow_id():
    async with session_scope() as db:
        t = await db.scalar(select(Tenant).where(Tenant.slug == "the-bakiroo", Tenant.source == "self"))
        print(t.id if t else "")

asyncio.run({"hold": hold, "quote": quote, "cleanup": cleanup, "flow_id": flow_id}[sys.argv[1]]())
