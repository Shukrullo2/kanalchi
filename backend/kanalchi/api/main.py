"""FastAPI application: REST + SSE for all three views, bot webhooks, internal endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse

from kanalchi.api.routers import admin, auth, internal, onboarding, viewer, webhooks
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
    openapi_url="/api/openapi.json",
)

app.include_router(internal.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(onboarding.router)
app.include_router(viewer.router)
app.include_router(webhooks.router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return {"ok": True}


@app.middleware("http")
async def strip_client_tenant_headers(request: Request, call_next):  # noqa: ANN001, ANN201
    # Never trust x-tenant-* from the public internet: Caddy is in front, but belt and braces.
    if (
        "x-tenant-host" in request.headers
        and request.client
        and request.client.host not in {"127.0.0.1", "::1"}
    ):
        fwd = request.headers.get("x-forwarded-for")
        if fwd:  # came through Caddy from a browser → drop the header
            request.scope["headers"] = [(k, v) for k, v in request.scope["headers"] if k != b"x-tenant-host"]
    return await call_next(request)
