"""`kanalchi` command line: migrations, workers, admin bootstrap, dev seeding, key rotation."""

from __future__ import annotations

import asyncio
import subprocess
import sys

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def migrate() -> None:
    """Apply Alembic migrations and the procrastinate schema (idempotent)."""
    from sqlalchemy import text

    from kanalchi.core.db import get_engine
    from kanalchi.jobs.app import app as pq

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    async def _apply() -> None:
        async with get_engine().connect() as conn:
            present = await conn.scalar(
                text("select count(*) from information_schema.tables where table_name = 'procrastinate_jobs'")
            )
        if present:
            typer.echo("procrastinate schema already present")
            return
        async with pq.open_async():
            await pq.schema_manager.apply_schema_async()
        typer.echo("procrastinate schema applied")

    asyncio.run(_apply())


@app.command()
def worker(
    kind: str = typer.Argument(..., help="telegram | index | publish"),
    concurrency: int | None = None,
) -> None:
    """Run a worker process for the given queue group."""
    from kanalchi.jobs.runner import run_worker

    if kind not in {"telegram", "index", "publish"}:
        raise typer.BadParameter("kind must be telegram, index or publish")
    asyncio.run(run_worker(kind, concurrency))


@app.command("gen-keys")
def gen_keys() -> None:
    """Print fresh APP_MASTER_KEY and SESSION_SECRET values."""
    import secrets

    from kanalchi.core.crypto import generate_key

    typer.echo(f"APP_MASTER_KEY={generate_key()}")
    typer.echo(f"SESSION_SECRET={secrets.token_urlsafe(48)}")


@app.command("create-admin")
def create_admin(tg_user_id: int, note: str = "") -> None:
    """Allow a Telegram user id into the admin panel."""
    from sqlalchemy.dialects.postgresql import insert

    from kanalchi.core.db import session_scope
    from kanalchi.core.models import PlatformAdmin

    async def _run() -> None:
        async with session_scope() as db:
            stmt = insert(PlatformAdmin).values(tg_user_id=tg_user_id, note=note or None)
            await db.execute(stmt.on_conflict_do_nothing())
        typer.echo(f"platform admin {tg_user_id} ensured")

    asyncio.run(_run())


def _entity(text: str, needle: str, kind: str) -> dict:
    """Telegram entity offsets are UTF-16 code units, so measure the prefix the way Telegram does."""
    i = text.index(needle)
    return {
        "_": kind,
        "offset": len(text[:i].encode("utf-16-le")) // 2,
        "length": len(needle.encode("utf-16-le")) // 2,
    }


def _sample(text: str, *specs: tuple[str, str]) -> tuple[str, list[dict]]:
    return text, [_entity(text, needle, kind) for needle, kind in specs]


SEED_SAMPLES = [
    _sample(
        "Toshkent shahar hokimligi yangi qurilish loyihasini e'lon qildi. Batafsil: gazeta.uz",
        ("Toshkent shahar hokimligi", "MessageEntityBold"),
        ("gazeta.uz", "MessageEntityUrl"),
    ),
    _sample(
        "Министерство юстиции опубликовало проект закона. Обсуждение открыто до конца месяца.",
        ("Министерство юстиции", "MessageEntityItalic"),
    ),
    _sample(
        "Ўзбекистон Республикаси Президенти фармони эълон қилинди.",
        ("Президенти фармони", "MessageEntityBold"),
    ),
    _sample(
        "Breaking: the central bank raised the key rate to 14%.\n\nWhat it means for deposits — a short thread.",
        ("Breaking:", "MessageEntityBold"),
        ("a short thread", "MessageEntityItalic"),
    ),
    _sample(
        "Bugun poytaxtda havo harorati +32°C. Ertaga yomg'ir kutilmoqda ☔️",
        ("+32°C", "MessageEntityBold"),
    ),
    _sample(
        "Yangi startap Toshkentda ochildi: dasturchilar uchun kovorking.\n\n#startap #toshkent",
        ("#startap", "MessageEntityHashtag"),
        ("#toshkent", "MessageEntityHashtag"),
    ),
]


@app.command("seed-dev")
def seed_dev(domain: str = "demo.localhost", title: str = "Demo kanal", posts: int = 0) -> None:
    """Create a demo tenant for local development, optionally with synthetic posts."""
    import random
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    from kanalchi.core.db import session_scope
    from kanalchi.core.models import Channel, Post, Tenant
    from kanalchi.telegram.ingest import engagement
    from kanalchi.text.normalize import normalize
    from kanalchi.text.tg_html import entities_to_html

    async def _run() -> None:
        async with session_scope() as db:
            tenant = await db.scalar(select(Tenant).where(Tenant.domain == domain))
            if tenant is None:
                tenant = Tenant(slug=domain.split(".")[0], domain=domain, title=title, status="active")
                db.add(tenant)
                await db.flush()
                typer.echo(f"created tenant {domain} (id={tenant.id})")
            else:
                typer.echo(f"tenant {domain} exists (id={tenant.id})")
            if not posts:
                return

            channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant.id))
            if channel is None:
                channel = Channel(
                    tenant_id=tenant.id,
                    tg_channel_id=1_000_000 + tenant.id,
                    username="demo_channel",
                    title=title,
                    about="Demo channel used for local development.",
                    backfill_status="done",
                    participants_count=12345,
                )
                db.add(channel)
                await db.flush()

            start = (
                await db.scalar(select(func.max(Post.tg_message_id)).where(Post.channel_id == channel.id))
                or 0
            )
            now = datetime.now(UTC)
            rng = random.Random(42)
            for i in range(1, posts + 1):
                text, entities = SEED_SAMPLES[(start + i) % len(SEED_SAMPLES)]
                views = rng.randint(500, 50_000)
                forwards = rng.randint(0, 120)
                reactions = [
                    {"emoji": e, "count": rng.randint(1, 300)}
                    for e in rng.sample(["👍", "🔥", "❤️", "😁"], k=rng.randint(1, 3))
                ]
                reactions_total = sum(r["count"] for r in reactions)
                db.add(
                    Post(
                        tenant_id=tenant.id,
                        channel_id=channel.id,
                        tg_message_id=start + i,
                        text=text,
                        text_norm=normalize(text),
                        entities=entities,
                        html=entities_to_html(text, entities),
                        date=now - timedelta(hours=6 * (posts - i)),
                        views=views,
                        forwards=forwards,
                        reactions=reactions,
                        reactions_total=reactions_total,
                        engagement_score=engagement(views, forwards, reactions_total),
                        media_kind="none",
                        content_hash=f"seed{start + i}",
                        index_status="pending",
                    )
                )
            channel.backfill_checkpoint = start + posts
            channel.backfill_total_estimate = start + posts
            typer.echo(f"seeded {posts} posts into channel {channel.id}")

    asyncio.run(_run())


@app.command("rotate-keys")
def rotate_keys() -> None:
    """Re-encrypt sessions and bot tokens with the primary APP_MASTER_KEY (set APP_MASTER_KEY_PREV first)."""
    from sqlalchemy import select

    from kanalchi.core.crypto import rotate
    from kanalchi.core.db import session_scope
    from kanalchi.core.models import TelegramAccount, Tenant

    async def _run() -> None:
        rotated = 0
        async with session_scope() as db:
            for acc in (await db.scalars(select(TelegramAccount))).all():
                if acc.session_enc:
                    acc.session_enc = rotate(acc.session_enc)
                    rotated += 1
            for tenant in (await db.scalars(select(Tenant))).all():
                if tenant.bot_token_enc:
                    tenant.bot_token_enc = rotate(tenant.bot_token_enc)
                    rotated += 1
        typer.echo(f"rotated {rotated} secrets")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
