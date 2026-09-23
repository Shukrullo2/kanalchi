"""Anthropic client, request defaults and usage accounting.

Every call here records its `usage` in `usage_ledger` so the admin costs view and the per-tenant
budgets are driven by measured spend, never estimates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

import anthropic
from sqlalchemy.dialects.postgresql import insert

from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import UsageLedger
from kanalchi.core.pricing import Usage, cost_usd
from kanalchi.core.settings import get_settings

log = get_logger(__name__)

Effort = Literal["low", "medium", "high", "xhigh", "max"]
Purpose = Literal[
    "chat_viewer",
    "chat_research",
    "draft",
    "extract",
    "map",
    "taxonomy",
    "discovery",
    "summary",
    "voice",
    "embed",
]

_client: anthropic.AsyncAnthropic | None = None

# Opus 5 may decline a request (stop_reason="refusal"); the server-side fallback re-runs it on
# another model inside the same call so a single policy decline does not break a user-facing feature.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        s = get_settings()
        if not s.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        _client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key, max_retries=3)
    return _client


def system_blocks(*texts: str, cache: bool = True, ttl: str | None = None) -> list[dict[str, Any]]:
    """System prompt as blocks, with the cache breakpoint on the last (stable) block.

    Order matters: put the most stable text first so a change late in the prompt does not
    invalidate everything before it.
    """
    blocks: list[dict[str, Any]] = [{"type": "text", "text": t} for t in texts if t]
    if blocks and cache:
        cc: dict[str, Any] = {"type": "ephemeral"}
        if ttl:
            cc["ttl"] = ttl
        blocks[-1]["cache_control"] = cc
    return blocks


def json_format(schema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "json_schema", "schema": schema}


async def record_usage(
    tenant_id: int | None,
    model: str,
    purpose: Purpose,
    usage: Usage,
    *,
    batch: bool = False,
    provider: str = "anthropic",
    cost: float | None = None,
    requests: int = 1,
) -> float:
    """Upsert-increment today's ledger row and return the cost in USD."""
    usd = cost if cost is not None else cost_usd(model, usage, batch=batch)
    values = {
        "tenant_id": tenant_id,
        "day": datetime.now(UTC).date(),
        "provider": provider,
        "model": model,
        "purpose": purpose,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "requests": requests,
        "cost_usd": usd,
    }
    stmt = insert(UsageLedger).values(**values)
    async with session_scope() as db:
        await db.execute(
            stmt.on_conflict_do_update(
                constraint="uq_usage_ledger_key",
                set_={
                    c: UsageLedger.__table__.c[c] + stmt.excluded[c]
                    for c in (
                        "input_tokens",
                        "output_tokens",
                        "cache_write_tokens",
                        "cache_read_tokens",
                        "requests",
                        "cost_usd",
                    )
                },
            )
        )
    return usd


async def complete_json(
    *,
    tenant_id: int | None,
    purpose: Purpose,
    system: list[dict[str, Any]],
    user: str | list[dict[str, Any]],
    schema: dict[str, Any],
    model: str | None = None,
    effort: Effort = "high",
    max_tokens: int = 16000,
    stream: bool = True,
) -> tuple[dict[str, Any] | None, float]:
    """One structured-output call. Returns (parsed JSON, cost). Streams by default so long
    high-effort calls never hit an HTTP timeout."""
    import json

    s = get_settings()
    client = get_client()
    model = model or s.chat_model
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort, "format": json_format(schema)},
    }
    if stream:
        async with client.messages.stream(**kwargs) as s_:
            message = await s_.get_final_message()
    else:
        message = await client.messages.create(**kwargs)

    usd = await record_usage(tenant_id, model, purpose, Usage.from_response(message.usage))
    if message.stop_reason == "refusal":
        log.warning(
            "claude.refusal",
            purpose=purpose,
            model=model,
            details=str(getattr(message, "stop_details", None)),
        )
        return None, usd
    text = next((b.text for b in message.content if b.type == "text"), "")
    if message.stop_reason == "max_tokens":
        # The JSON is not malformed, it is unfinished. Saying "bad json" here sent
        # me looking at the schema while the answer was that the ceiling was too low.
        log.warning(
            "claude.truncated",
            purpose=purpose,
            model=model,
            max_tokens=max_tokens,
            output_tokens=message.usage.output_tokens,
        )
        return None, usd
    try:
        return json.loads(text), usd
    except json.JSONDecodeError:
        log.warning("claude.bad_json", purpose=purpose, model=model, head=text[:200])
        return None, usd


async def count_tokens(model: str, system: list[dict[str, Any]], user: str) -> int:
    resp = await get_client().messages.count_tokens(
        model=model, system=system, messages=[{"role": "user", "content": user}]
    )
    return int(resp.input_tokens)


def utcnow() -> datetime:
    return datetime.now(UTC)
