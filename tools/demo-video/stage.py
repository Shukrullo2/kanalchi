"""Stage the local database so the demo can price @the_bakiroo on the public /start form, then put it back."""
import asyncio, sys
from sqlalchemy import select, delete
from kanalchi.core.db import session_scope
from kanalchi.core.models import Tenant, ChannelQuote
from kanalchi.core.billing import quote_for_posts

async def hold():
    # The channel is onboarded locally, which the form refuses to price; park it for the recording.
    async with session_scope() as db:
        t = await db.get(Tenant, 3)
        if t.status == "active":
            t.status = "onboarding"
        await db.execute(delete(ChannelQuote).where(ChannelQuote.username == "the_bakiroo"))
        print("held", t.status)

async def finalize():
    # What the reader account would have measured (no worker runs locally).
    async with session_scope() as db:
        row = await db.scalar(select(ChannelQuote).where(ChannelQuote.username == "the_bakiroo"))
        if row is None:
            print("no row"); return
        row.quote = quote_for_posts(12965, source="telegram", avg_post_tokens=321, text_share=0.947)
        row.status, row.error = "done", None
        row.title = row.title or "bakiroo"
        row.participants_count = row.participants_count or 60382
        print("finalized", row.quote["price_uzs"])

async def cleanup():
    async with session_scope() as db:
        t = await db.get(Tenant, 3)
        if t.status == "onboarding":
            t.status = "active"
        await db.execute(delete(ChannelQuote).where(ChannelQuote.username == "the_bakiroo"))
        print("restored", t.status)

asyncio.run({"hold": hold, "finalize": finalize, "cleanup": cleanup}[sys.argv[1]]())
