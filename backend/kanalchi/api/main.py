"""FastAPI application: REST + SSE for all three views, bot webhooks, internal endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse

from kanalchi.api.routers import (
    admin,
    auth,
    chat,
    graph,
    internal,
    onboarding,
    signup,
    studio,
    tags,
    viewer,
    webhooks,
)
from kanalchi.core.db import dispose_engine
from kanalchi.core.logging import configure_logging, get_logger
from kanalchi.core.redis import close_redis
from kanalchi.core.settings import get_settings
from kanalchi.jobs.app import app as job_app

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    configure_logging()
    s = get_settings()
    log.info("api.start", env=s.env, admin_host=s.admin_host)
    async with job_app.open_async():  # lets request handlers defer jobs
        yield
    await close_redis()
    await dispose_engine()


app = FastAPI(
    title="Kanalchi API",
    version="0.1.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
    docs_url="/api/docs" if get_settings().is_dev else None,
    openapi_url="/api/openapi.json" if get_settings().is_dev else None,
)

app.include_router(internal.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(onboarding.router)
app.include_router(signup.router)
app.include_router(viewer.router)
app.include_router(tags.router)
app.include_router(graph.router)
app.include_router(chat.router)
app.include_router(studio.router)
app.include_router(webhooks.router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return {"ok": True}


@app.middleware("http")
async def strip_client_tenant_headers(request: Request, call_next):  # noqa: ANN001, ANN201
    """Never trust x-tenant-* from the public internet.

    Caddy already drops the header on the way in (Caddyfile: `header_up -X-Tenant-Host`); this
    is the second line. Anything that arrived through a proxy carries X-Forwarded-For, whereas the
    Next.js server calls the API directly and does not. In development the Next dev server *is*
    a proxy (next.config rewrites /api/* and adds X-Forwarded-For), so the check is skipped there.
    """
    if (
        "x-tenant-host" in request.headers
        and "x-forwarded-for" in request.headers
        and not get_settings().is_dev
    ):
        request.scope["headers"] = [(k, v) for k, v in request.scope["headers"] if k != b"x-tenant-host"]
    return await call_next(request)
