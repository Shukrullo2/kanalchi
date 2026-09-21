"""Streaming agent loop for viewer and research chat.

The loop is written by hand rather than using the SDK tool runner because each turn has to emit
SSE events as it happens, execute tools concurrently, validate citations against what the tools
actually returned, and record spend, all while staying resumable if the reader disconnects.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from kanalchi.ai.chat import prompts
from kanalchi.ai.chat.tools import ToolBox, tool_definitions
from kanalchi.ai.claude import FALLBACK_BETA, get_client, record_usage, system_blocks
from kanalchi.ai.taxonomy import taxonomy_summary
from kanalchi.core.db import session_scope
from kanalchi.core.limits import add_platform_spend, add_spend, get_budget
from kanalchi.core.logging import get_logger
from kanalchi.core.models import ChatMessage, ChatSession, Post, Tenant
from kanalchi.core.pricing import Usage, cost_usd
from kanalchi.core.settings import get_settings

log = get_logger(__name__)

MAX_TOOL_ROUNDS = 8
MAX_TOKENS = 16000
HISTORY_TURNS = 20
CITATION_RE = re.compile(r"\[\[post:(\d+)\]\]")


@dataclass(slots=True)
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def sse(self) -> str:
        return f"event: {self.type}\ndata: {json.dumps(self.data, ensure_ascii=False, default=str)}\n\n"


async def _channel_stats(tenant_id: int) -> dict[str, Any]:
    from sqlalchemy import func

    async with session_scope() as db:
        row = (
            await db.execute(
                select(func.count(Post.id), func.min(Post.date), func.max(Post.date)).where(
                    Post.tenant_id == tenant_id, Post.is_deleted.is_(False), Post.is_album_root.is_(True)
                )
            )
        ).first()
    return {
        "posts": row[0] if row else 0,
        "first_post": row[1].date().isoformat() if row and row[1] else None,
        "last_post": row[2].date().isoformat() if row and row[2] else None,
    }


async def build_system(tenant: Tenant, kind: str) -> list[dict[str, Any]]:
    """Cached prefix: instructions, channel profile, taxonomy. Most stable first."""
    settings = tenant.settings or {}
    blocks = [
        prompts.VIEWER_ROLE if kind == "viewer" else prompts.RESEARCH_ROLE,
        prompts.channel_block(settings.get("channel_profile"), await _channel_stats(tenant.id)),
        prompts.taxonomy_block(await taxonomy_summary(tenant.id)),
    ]
    if kind == "research":
        blocks.append(prompts.voice_block(settings.get("voice_profile")))
    return system_blocks(*[b for b in blocks if b], ttl="1h")


async def load_history(session_id: Any, limit: int = HISTORY_TURNS) -> list[dict[str, Any]]:
    """Replay stored content blocks verbatim so tool results stay attached to their tool_use ids."""
    async with session_scope() as db:
        rows = (
            await db.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.desc())
                .limit(limit * 2)
            )
        ).all()
    messages: list[dict[str, Any]] = []
    for row in reversed(rows):
        content = row.content_blocks or ([{"type": "text", "text": row.content}] if row.content else [])
        if content:
            messages.append({"role": row.role, "content": content})
    # A turn must not begin with tool results left over from a truncated history.
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    return messages


@dataclass
class TurnResult:
    text: str = ""
    citations: list[int] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    tool_turns: list[dict[str, Any]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    stop_reason: str | None = None


def validate_citations(text: str, allowed: set[int]) -> tuple[str, list[int]]:
    """Drop any citation the tools did not actually return, so a marker always resolves to a real post."""
    used: list[int] = []

    def replace(match: re.Match[str]) -> str:
        post_id = int(match.group(1))
        if post_id in allowed:
            if post_id not in used:
                used.append(post_id)
            return match.group(0)
        log.info("chat.citation_dropped", post_id=post_id)
        return ""

    cleaned = CITATION_RE.sub(replace, text)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip(), used


async def run_turn(
    *,
    tenant: Tenant,
    session_id: Any,
    user_text: str,
    kind: str,
    locale: str,
    budget_note: str | None = None,
) -> AsyncIterator[Event]:
    """Yields SSE events for one user message. Persists the assistant message before finishing."""
    s = get_settings()
    started = time.monotonic()
    toolbox = ToolBox(tenant.id, locale)

    # Everything before the first token can fail too (missing API key, database hiccup while
    # assembling the prompt). Surface that as an error event rather than an empty stream.
    try:
        client = get_client()
        tools = tool_definitions(kind)
        system = await build_system(tenant, kind)
        history = await load_history(session_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("chat.setup_failed", tenant_id=tenant.id, error=str(exc)[:300])
        yield Event("start", {"session_id": str(session_id)})
        yield Event("error", {"code": "unavailable", "message": "the assistant is not configured yet"})
        yield Event("done", {"stop_reason": "error"})
        return

    messages: list[dict[str, Any]] = [
        *history,
        {"role": "user", "content": user_text},
        # Volatile per-turn facts live here, never in the cached prefix.
        {
            "role": "system",
            "content": prompts.turn_context(
                today=datetime.now(UTC).date().isoformat(), locale=locale, budget_note=budget_note
            ),
        },
    ]

    request: dict[str, Any] = {
        "model": s.chat_model,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "tools": tools,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "medium" if kind == "viewer" else "high"},
    }
    if s.enable_refusal_fallbacks:
        request["betas"] = [FALLBACK_BETA]
        request["fallbacks"] = "default"

    result = TurnResult()
    yield Event("start", {"session_id": str(session_id)})

    for _round in range(MAX_TOOL_ROUNDS):
        assistant_blocks: list[dict[str, Any]] = []
        stop_reason: str | None = None
        try:
            stream_ctx = (
                client.beta.messages.stream(messages=messages, **request)
                if s.enable_refusal_fallbacks
                else client.messages.stream(messages=messages, **request)
            )
            async with stream_ctx as stream:
                async for event in stream:
                    if event.type == "text" and event.text:
                        result.text += event.text
                        yield Event("delta", {"text": event.text})
                message = await stream.get_final_message()
        except Exception as exc:  # noqa: BLE001
            log.exception("chat.stream_failed", tenant_id=tenant.id, error=str(exc)[:300])
            yield Event("error", {"code": "upstream", "message": "the assistant is unavailable right now"})
            yield Event("done", {"stop_reason": "error"})
            return

        usage = Usage.from_response(message.usage)
        result.usage = Usage(
            input_tokens=result.usage.input_tokens + usage.input_tokens,
            output_tokens=result.usage.output_tokens + usage.output_tokens,
            cache_write_tokens=result.usage.cache_write_tokens + usage.cache_write_tokens,
            cache_read_tokens=result.usage.cache_read_tokens + usage.cache_read_tokens,
        )
        result.cost_usd += cost_usd(s.chat_model, usage)
        stop_reason = message.stop_reason
        assistant_blocks = [b.model_dump() for b in message.content]
        messages.append({"role": "assistant", "content": assistant_blocks})
        result.blocks.extend(assistant_blocks)

        if stop_reason == "refusal":
            result.stop_reason = "refusal"
            yield Event("error", {"code": "refusal", "message": "I can't help with that one."})
            break

        tool_uses = [b for b in assistant_blocks if b.get("type") == "tool_use"]
        if not tool_uses:
            result.stop_reason = stop_reason
            break

        if stop_reason == "max_tokens":
            result.stop_reason = "max_tokens"
            yield Event("error", {"code": "truncated", "message": "the answer was cut short"})
            break

        for block in tool_uses:
            yield Event("tool_call", {"name": block["name"], "input": block.get("input", {})})

        outputs = await asyncio.gather(
            *[toolbox.run(b["name"], b.get("input") or {}) for b in tool_uses], return_exceptions=True
        )
        tool_results: list[dict[str, Any]] = []
        for block, output in zip(tool_uses, outputs, strict=True):
            failed = isinstance(output, BaseException)
            payload = json.dumps({"error": str(output)}) if failed else str(output)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block["id"], "content": payload, "is_error": failed}
            )
            yield Event("tool_result", {"name": block["name"], "ok": not failed, "size": len(payload)})

        messages.append({"role": "user", "content": tool_results})
        result.tool_turns.append({"role": "user", "content": tool_results})
        result.blocks.extend(tool_results)
    else:
        yield Event("error", {"code": "tool_limit", "message": "stopped after too many lookups"})

    # Citations are only trustworthy if the ids came from this turn's tool results.
    cleaned, citations = validate_citations(result.text, toolbox.seen_post_ids)
    result.text, result.citations = cleaned, citations

    await record_usage(
        tenant.id, s.chat_model, "chat_viewer" if kind == "viewer" else "chat_research", result.usage
    )
    budget_kind = "chat" if kind == "viewer" else "studio"
    await add_spend(tenant.id, budget_kind, result.cost_usd)
    await add_platform_spend(result.cost_usd)

    cited = await _citation_cards(tenant.id, citations)
    if cited:
        yield Event("citations", {"posts": cited})

    await _persist(session_id, tenant.id, user_text, result, int((time.monotonic() - started) * 1000))

    yield Event(
        "usage",
        {
            "input": result.usage.input_tokens,
            "cache_read": result.usage.cache_read_tokens,
            "output": result.usage.output_tokens,
            "usd": round(result.cost_usd, 5),
        },
    )
    yield Event("done", {"stop_reason": result.stop_reason})


async def _citation_cards(tenant_id: int, post_ids: list[int]) -> list[dict[str, Any]]:
    if not post_ids:
        return []
    from kanalchi.core.models import Channel

    async with session_scope() as db:
        channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
        if channel is None:
            return []
        rows = (
            await db.scalars(
                select(Post).where(Post.channel_id == channel.id, Post.tg_message_id.in_(post_ids))
            )
        ).all()
    by_id = {p.tg_message_id: p for p in rows}
    cards = []
    for post_id in post_ids:
        p = by_id.get(post_id)
        if p is None:
            continue
        cards.append(
            {
                "id": p.tg_message_id,
                "date": p.date.isoformat(),
                "title": p.title or " ".join((p.text or "").split())[:80],
                "url": f"/post/{p.tg_message_id}",
            }
        )
    return cards


async def _persist(
    session_id: Any, tenant_id: int, user_text: str, result: TurnResult, latency_ms: int
) -> None:
    s = get_settings()
    async with session_scope() as db:
        db.add(
            ChatMessage(
                tenant_id=tenant_id,
                session_id=session_id,
                role="user",
                content=user_text,
                content_blocks=[{"type": "text", "text": user_text}],
            )
        )
        db.add(
            ChatMessage(
                tenant_id=tenant_id,
                session_id=session_id,
                role="assistant",
                content=result.text,
                content_blocks=result.blocks,
                citations=result.citations,
                model=s.chat_model,
                usage=result.usage.as_dict(),
                cost_usd=result.cost_usd,
                stop_reason=result.stop_reason,
                latency_ms=latency_ms,
            )
        )
        session = await db.get(ChatSession, session_id)
        if session is not None:
            session.message_count = (session.message_count or 0) + 2
            session.total_cost_usd = float(session.total_cost_usd or 0) + result.cost_usd
            session.last_message_at = datetime.now(UTC)
            if not session.title:
                session.title = " ".join(user_text.split())[:80]


async def budget_note(tenant: Tenant, kind: str) -> tuple[str | None, bool]:
    """(note for the model, blocked). The note only appears when the tenant is close to its cap."""
    s = get_settings()
    limit = float(
        (tenant.daily_chat_budget_usd if kind == "viewer" else tenant.daily_studio_budget_usd)
        or (s.default_daily_chat_budget_usd if kind == "viewer" else s.default_daily_studio_budget_usd)
    )
    state = await get_budget(tenant.id, "chat" if kind == "viewer" else "studio", limit)
    if state.exhausted:
        return None, True
    if state.warning:
        return "Answer briefly today: this channel is close to its daily assistant budget.", False
    return None, False
