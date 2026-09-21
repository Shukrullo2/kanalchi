"""Admin-facing job records (`job_runs`) wrapped around procrastinate tasks."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from kanalchi.core.db import session_scope
from kanalchi.core.models import JobRun


async def create_job_run(tenant_id: int | None, type_: str, params: dict[str, Any] | None = None) -> int:
    async with session_scope() as db:
        jr = JobRun(tenant_id=tenant_id, type=type_, status="queued", params=params or {}, progress={})
        db.add(jr)
        await db.flush()
        return jr.id


async def update_job_run(job_run_id: int | None, **values: Any) -> None:
    if job_run_id is None:
        return
    async with session_scope() as db:
        jr = await db.get(JobRun, job_run_id)
        if jr is None:
            return
        progress = values.pop("progress", None)
        if progress is not None:
            jr.progress = {**(jr.progress or {}), **progress}
        for k, v in values.items():
            setattr(jr, k, v)


@contextlib.asynccontextmanager
async def job_run(job_run_id: int | None) -> AsyncIterator[None]:
    await update_job_run(job_run_id, status="running", started_at=datetime.now(UTC), error=None)
    try:
        yield
    except Exception as exc:
        await update_job_run(
            job_run_id, status="failed", finished_at=datetime.now(UTC), error=str(exc)[:2000]
        )
        raise
    else:
        await update_job_run(job_run_id, status="succeeded", finished_at=datetime.now(UTC))
