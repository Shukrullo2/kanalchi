"""`kanalchi` command line: migrations, workers, admin bootstrap, key generation."""

from __future__ import annotations

import asyncio
import subprocess
import sys

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def migrate() -> None:
    """Apply Alembic migrations and the procrastinate schema (idempotent)."""
    from kanalchi.jobs.app import app as pq

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    async def _apply() -> None:
        from sqlalchemy import text

        from kanalchi.core.db import get_engine

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
    kind: str = typer.Argument(..., help="telegram | index | publish"), concurrency: int | None = None
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


@app.command("seed-dev")
def seed_dev(domain: str = "demo.localhost", title: str = "Demo kanal") -> None:
    """Create a demo tenant for local development (no Telegram wiring yet)."""
    from sqlalchemy import select

    from kanalchi.core.db import session_scope
    from kanalchi.core.models import Tenant

    async def _run() -> None:
        async with session_scope() as db:
            existing = await db.scalar(select(Tenant).where(Tenant.domain == domain))
            if existing:
                typer.echo(f"tenant {domain} already exists (id={existing.id})")
                return
            t = Tenant(slug=domain.split(".")[0], domain=domain, title=title, status="active")
            db.add(t)
            await db.flush()
            typer.echo(f"created tenant {domain} (id={t.id})")

    asyncio.run(_run())


@app.command("rotate-keys")
def rotate_keys() -> None:
    """Re-encrypt sessions and bot tokens with the primary APP_MASTER_KEY (run after adding APP_MASTER_KEY_PREV)."""
    from sqlalchemy import select

    from kanalchi.core.crypto import rotate
    from kanalchi.core.db import session_scope
    from kanalchi.core.models import TelegramAccount, Tenant

    async def _run() -> None:
        n = 0
        async with session_scope() as db:
            for acc in (await db.scalars(select(TelegramAccount))).all():
                if acc.session_enc:
                    acc.session_enc = rotate(acc.session_enc)
                    n += 1
            for t in (await db.scalars(select(Tenant))).all():
                if t.bot_token_enc:
                    t.bot_token_enc = rotate(t.bot_token_enc)
                    n += 1
        typer.echo(f"rotated {n} secrets")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
