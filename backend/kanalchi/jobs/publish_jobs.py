"""Jobs executed inside worker-publish: scheduled posting and blogger notifications."""

from __future__ import annotations

from typing import Any

from kanalchi.core.logging import get_logger
from kanalchi.jobs.app import app

log = get_logger(__name__)


@app.task(queue="publish", name="publish.ping")
async def ping(payload: str = "pong") -> str:
    log.info("publish.ping", payload=payload)
    return payload


@app.task(queue="publish", name="publish.draft", retry=0)
async def publish(draft_id: int) -> dict[str, Any]:
    """Send one draft. Retries are handled inside, so the job itself never retries blindly:
    re-sending a post that already went out would double-post to the channel."""
    from kanalchi.telegram.publish import publish_draft

    result = await publish_draft(draft_id)
    if result.get("failed"):
        await notify_failure.defer_async(draft_id=draft_id)
    return result


@app.task(queue="notify", name="notify.publish_failed", retry=1)
async def notify_failure(draft_id: int) -> None:
    from kanalchi.core.db import session_scope
    from kanalchi.core.models import Draft
    from kanalchi.telegram.publish import notify_failure as _notify

    async with session_scope() as db:
        draft = await db.get(Draft, draft_id)
        tenant_id = draft.tenant_id if draft else None
    if tenant_id:
        await _notify(tenant_id, draft_id)


@app.task(queue="publish", name="publish.build_voice", retry=0)
async def build_voice(tenant_id: int, job_run_id: int | None = None) -> dict[str, Any]:
    from kanalchi.ai.drafting import build_voice_profile
    from kanalchi.core.jobs import job_run

    async with job_run(job_run_id):
        return await build_voice_profile(tenant_id)
