"""Run a second model over posts the primary model has already extracted, and diff.

The question a price list cannot answer is whether a cheaper model is good enough
at *this* job, and a cheaper model will almost always return schema-valid JSON —
so validity tells you nothing. What matters is whether it finds the same entities.

Script drift is not the risk it looks like: `normalize()` already folds
"Марказий банк" onto "markaziy bank", so a model that echoes Cyrillic still lands
on the right tag. What normalization cannot repair is an entity the model never
found, one it made up, an abbreviation it left unexpanded ("CBU" does not fold
onto "markaziy bank"), or one it filed as a person when it is a government body.
Those are what this scores.

The candidate sees the identical system prompt, user content and schema; only the
model, and the thinking settings that model accepts, differ.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy import select

from kanalchi.ai.claude import get_client
from kanalchi.ai.extraction import _posts_payload, _request, build_prompt
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Extraction, Post
from kanalchi.core.pricing import Usage, cost_usd
from kanalchi.text.normalize import normalize

log = get_logger(__name__)


async def _extracted_sample(tenant_id: int, limit: int) -> list[tuple[int, dict[str, Any], dict[str, Any]]]:
    """(post_id, baseline result, baseline usage) for posts already extracted, newest first."""
    async with session_scope() as db:
        rows = (
            await db.execute(
                select(Extraction.post_id, Extraction.result, Extraction.usage)
                .join(Post, Post.id == Extraction.post_id)
                .where(
                    Extraction.tenant_id == tenant_id,
                    Extraction.status == "succeeded",
                    Extraction.result.is_not(None),
                )
                .order_by(Post.date.desc())
                .limit(limit)
            )
        ).all()
    return [(pid, result, usage or {}) for pid, result, usage in rows]


def _entity_names(result: dict[str, Any]) -> set[str]:
    """Normalized entity names, which is what the tag index is actually built from."""
    return {
        normalize(e.get("normalized") or e.get("surface") or "")
        for e in (result.get("entities") or [])
        if (e.get("normalized") or e.get("surface"))
    }


def _typed_entities(result: dict[str, Any]) -> set[tuple[str, str]]:
    """(normalized name, type) — a ministry filed as a person is a different tag."""
    out = set()
    for e in result.get("entities") or []:
        name = normalize(e.get("normalized") or e.get("surface") or "")
        if name:
            out.add((name, e.get("type") or "other"))
    return out


def _themes(result: dict[str, Any]) -> set[str]:
    return {normalize(t.get("name", "")) for t in (result.get("themes") or []) if t.get("name")}


def _score(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    b_ents, c_ents = _entity_names(baseline), _entity_names(candidate)
    b_themes, c_themes = _themes(baseline), _themes(candidate)
    shared = b_ents & c_ents
    b_typed, c_typed = _typed_entities(baseline), _typed_entities(candidate)
    return {
        "entity_recall": len(shared) / len(b_ents) if b_ents else None,
        "entity_precision": len(shared) / len(c_ents) if c_ents else None,
        # Of the entities both found, how many were given the same type.
        "type_agreement": (len(b_typed & c_typed) / len(shared)) if shared else None,
        "missed": sorted(b_ents - c_ents),
        "invented": sorted(c_ents - b_ents),
        "theme_overlap": (len(b_themes & c_themes) / len(b_themes)) if b_themes else None,
        "format_agrees": baseline.get("format") == candidate.get("format"),
        "language_agrees": baseline.get("language_primary") == candidate.get("language_primary"),
        "low_content_agrees": baseline.get("is_low_content") == candidate.get("is_low_content"),
    }


async def compare_models(
    tenant_id: int, candidate_model: str, sample: int = 100, concurrency: int = 8
) -> dict[str, Any]:
    """Extract a sample with `candidate_model` and score it against what is already stored."""
    rows = await _extracted_sample(tenant_id, sample)
    if not rows:
        return {"error": "no completed extractions to compare against"}

    system, channel_title = await build_prompt(tenant_id)
    async with session_scope() as db:
        payloads = {p["id"]: p for p in await _posts_payload(db, [pid for pid, _, _ in rows], channel_title)}

    client = get_client()
    gate = asyncio.Semaphore(concurrency)
    baseline_usage = Usage()
    candidate_usage = Usage()

    async def run_one(post_id: int, baseline: dict[str, Any], b_usage: dict[str, Any]):
        payload = payloads.get(post_id)
        if payload is None:
            return None
        request = _request(payload, system, candidate_model)
        async with gate:
            try:
                message = await client.messages.create(**request["params"])
            except Exception as exc:  # noqa: BLE001
                log.warning("compare.failed", post_id=post_id, error=str(exc)[:200])
                return {"post_id": post_id, "failed": type(exc).__name__}
        text = "".join(b.text for b in message.content if b.type == "text")
        try:
            candidate = json.loads(text)
        except json.JSONDecodeError:
            return {"post_id": post_id, "failed": "invalid json"}

        nonlocal baseline_usage, candidate_usage
        baseline_usage = _add(baseline_usage, b_usage)
        candidate_usage = _add(
            candidate_usage,
            {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "cache_read_tokens": getattr(message.usage, "cache_read_input_tokens", 0) or 0,
            },
        )
        return {"post_id": post_id, **_score(baseline, candidate)}

    scored = [r for r in await asyncio.gather(*(run_one(*row) for row in rows)) if r]
    ok = [r for r in scored if "failed" not in r]
    return {
        "candidate_model": candidate_model,
        "sample": len(scored),
        "failed": len(scored) - len(ok),
        "entity_recall": _mean(ok, "entity_recall"),
        "entity_precision": _mean(ok, "entity_precision"),
        "type_agreement": _mean(ok, "type_agreement"),
        "theme_overlap": _mean(ok, "theme_overlap"),
        "format_agreement": _rate(ok, "format_agrees"),
        "language_agreement": _rate(ok, "language_agrees"),
        "low_content_agreement": _rate(ok, "low_content_agrees"),
        "baseline_cost_usd": round(cost_usd("claude-sonnet-5", baseline_usage, batch=True), 4),
        "candidate_cost_usd": round(cost_usd(candidate_model, candidate_usage, batch=False), 4),
        "worst": sorted((r for r in ok if r["entity_recall"] is not None), key=lambda r: r["entity_recall"])[
            :5
        ],
    }


def _add(total: Usage, raw: dict[str, Any]) -> Usage:
    return Usage(
        input_tokens=total.input_tokens + int(raw.get("input_tokens") or 0),
        output_tokens=total.output_tokens + int(raw.get("output_tokens") or 0),
        cache_read_tokens=total.cache_read_tokens + int(raw.get("cache_read_tokens") or 0),
    )


def _mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(values) / len(values), 3) if values else None


def _rate(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [bool(r.get(key)) for r in rows]
    return round(sum(values) / len(values), 3) if values else None
