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


@app.command("seed-tags")
def seed_tags(domain: str = "demo.localhost") -> None:
    """Attach a small hand-made taxonomy to the seeded posts (no API keys needed)."""
    from sqlalchemy import select

    from kanalchi.ai.discovery import ensure_universal_dimensions
    from kanalchi.ai.postprocess import apply_extraction
    from kanalchi.core.db import session_scope
    from kanalchi.core.models import Dimension, Post, Tag, TagAlias, Tenant
    from kanalchi.text.normalize import normalize
    from kanalchi.text.slug import slugify

    # canonical name -> (dimension, aliases) — the aliases are what make the cascade match
    TAGS = {
        "Toshkent": ("locations", ["Тошкент", "Ташкент", "Tashkent"]),
        "Toshkent shahar hokimligi": ("gov_orgs", ["Тошкент шаҳар ҳокимлиги", "hokimlik", "хокимият"]),
        "Adliya vazirligi": ("gov_orgs", ["Министерство юстиции", "Минюст", "Ministry of Justice"]),
        "O'zbekiston Prezidenti": ("gov_orgs", ["Президент", "Ўзбекистон Республикаси Президенти"]),
        "Markaziy bank": ("gov_orgs", ["Central Bank", "Центральный банк"]),
        "Qurilish": ("themes", ["construction", "строительство"]),
        "Qonunchilik": ("themes", ["legislation", "законодательство", "qonun"]),
        "Iqtisodiyot": ("themes", ["economy", "экономика"]),
        "Ob-havo": ("themes", ["weather", "погода"]),
        "Startaplar": ("themes", ["startups", "стартапы"]),
    }
    # tg_message_id % len(SEED_SAMPLES) -> extraction stand-in for that sample text
    SAMPLE_TAGS = {
        0: {
            "entities": [("location", "Toshkent"), ("gov_org", "Toshkent shahar hokimligi")],
            "themes": ["Qurilish"],
            "format": "news",
            "lang": "uz-Latn",
        },
        1: {
            "entities": [("gov_org", "Adliya vazirligi")],
            "themes": ["Qonunchilik"],
            "format": "announcement",
            "lang": "ru",
        },
        2: {
            "entities": [("gov_org", "O'zbekiston Prezidenti")],
            "themes": ["Qonunchilik"],
            "format": "announcement",
            "lang": "uz-Cyrl",
        },
        3: {
            "entities": [("gov_org", "Markaziy bank")],
            "themes": ["Iqtisodiyot"],
            "format": "news",
            "lang": "en",
        },
        4: {
            "entities": [("location", "Toshkent")],
            "themes": ["Ob-havo"],
            "format": "news",
            "lang": "uz-Latn",
        },
        5: {
            "entities": [("location", "Toshkent")],
            "themes": ["Startaplar"],
            "format": "news",
            "lang": "uz-Latn",
        },
    }

    async def _run() -> None:
        async with session_scope() as db:
            tenant = await db.scalar(select(Tenant).where(Tenant.domain == domain))
            if tenant is None:
                typer.echo(f"tenant {domain} not found; run seed-dev first")
                return
            tenant_id = tenant.id
        await ensure_universal_dimensions(tenant_id)

        async with session_scope() as db:
            dims = {
                k: v
                for k, v in (
                    await db.execute(
                        select(Dimension.key, Dimension.id).where(Dimension.tenant_id == tenant_id)
                    )
                ).all()
            }
            for canonical, (dim_key, aliases) in TAGS.items():
                norm = normalize(canonical)
                tag = await db.scalar(
                    select(Tag).where(Tag.tenant_id == tenant_id, Tag.canonical_norm == norm)
                )
                if tag is None:
                    tag = Tag(
                        tenant_id=tenant_id,
                        dimension_id=dims[dim_key],
                        slug=slugify(canonical),
                        canonical_name=canonical,
                        canonical_norm=norm,
                        labels={"uz": canonical, "ru": canonical, "en": canonical},
                        status="active",
                        source="taxonomy",
                    )
                    db.add(tag)
                    await db.flush()
                for alias in [canonical, *aliases]:
                    an = normalize(alias)
                    exists = await db.scalar(
                        select(TagAlias.id).where(TagAlias.tag_id == tag.id, TagAlias.alias_norm == an)
                    )
                    if not exists:
                        db.add(
                            TagAlias(
                                tenant_id=tenant_id,
                                tag_id=tag.id,
                                alias=alias,
                                alias_norm=an,
                                source="manual",
                            )
                        )

            posts = (
                await db.scalars(select(Post).where(Post.tenant_id == tenant_id).order_by(Post.tg_message_id))
            ).all()
            plan = [(p.id, SAMPLE_TAGS[p.tg_message_id % len(SEED_SAMPLES)]) for p in posts]

        for post_id, spec in plan:
            extraction = {
                "language_primary": spec["lang"],
                "format": spec["format"],
                "title": None,
                "summary": None,
                "themes": [{"name": t, "confidence": 0.9} for t in spec["themes"]],
                "entities": [
                    {
                        "type": kind,
                        "normalized": name,
                        "surface": name,
                        "lang": spec["lang"],
                        "role": "mentioned",
                        "sentiment_toward": None,
                        "confidence": 0.9,
                    }
                    for kind, name in spec["entities"]
                ],
                "custom": [],
                "hashtags": [],
                "taxonomy_mapped": [],
                "key_claims": [],
            }
            await apply_extraction(post_id, extraction)

        from kanalchi.ai.taxonomy import recompute_counts

        await recompute_counts(tenant_id)
        typer.echo(f"tagged {len(plan)} posts with {len(TAGS)} tags")

    asyncio.run(_run())


@app.command("tag-images")
def tag_images_cmd(tenant_id: int, limit: int = 500, posts: bool = True) -> None:
    """Find and store a picture for each subject in the index.

    Organisation logos come from the site the channel itself links to; people and
    places come from Wikidata. Everything is stored in our own bucket, so pages
    never wait on someone else's server.

    Whatever is left over then takes the best picture its own posts can offer,
    which `--no-posts` skips. That pass reads every candidate image out of the
    bucket, so it is much the slower of the two.
    """
    import asyncio
    import json as _json

    from kanalchi.tagimages import choose_post_pictures, fetch_images

    async def _run() -> dict:
        result = await fetch_images(tenant_id, limit=limit)
        if posts:
            result |= await choose_post_pictures(tenant_id)
        return result

    typer.echo(_json.dumps(asyncio.run(_run()), indent=2))


@app.command("compare-models")
def compare_models_cmd(
    tenant_id: int,
    candidate: str = "claude-haiku-4-5",
    sample: int = 100,
) -> None:
    """Score a cheaper model against what the primary model already extracted.

    Runs `candidate` over posts that already have a stored extraction and reports
    how much of the entity and theme labelling it reproduces, plus what each side
    cost. Spends real money on the candidate calls — a hundred posts on Haiku is
    a few tens of cents.
    """
    import asyncio
    import json as _json

    from kanalchi.ai.compare import compare_models

    report = asyncio.run(compare_models(tenant_id, candidate, sample=sample))
    typer.echo(_json.dumps(report, ensure_ascii=False, indent=2))


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
