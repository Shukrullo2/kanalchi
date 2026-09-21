"""Voice profile and AI drafting.

A draft is only useful if it sounds like the blogger, so both halves lean on their own archive: the
voice profile is derived from their posts, and every draft is grounded in the most similar earlier
posts rather than in the model's general knowledge.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from kanalchi.ai import prompts as extraction_prompts
from kanalchi.ai.chat import prompts as chat_prompts
from kanalchi.ai.claude import complete_json, system_blocks
from kanalchi.ai.schemas import VoiceProfile, schema_of
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, Post, Tenant
from kanalchi.search import hybrid
from kanalchi.telegram.formatting import markdown_to_telegram_html, sanitize

log = get_logger(__name__)

VOICE_SAMPLE = 60
CONTEXT_POSTS = 5


async def _voice_samples(tenant_id: int) -> list[str]:
    """Top-performing, recent and random posts: habits show up in all three, not just the hits."""
    async with session_scope() as db:
        base = select(Post.text).where(
            Post.tenant_id == tenant_id,
            Post.is_deleted.is_(False),
            Post.is_album_root.is_(True),
            func.length(Post.text) > 120,
        )
        top = (await db.scalars(base.order_by(Post.engagement_score.desc()).limit(20))).all()
        latest = (await db.scalars(base.order_by(Post.date.desc()).limit(10))).all()
        spread = (await db.scalars(base.order_by(func.random()).limit(30))).all()
    seen: set[str] = set()
    out: list[str] = []
    for text in [*top, *latest, *spread]:
        if text and text not in seen:
            seen.add(text)
            out.append(text[:1200])
    return out[:VOICE_SAMPLE]


async def build_voice_profile(tenant_id: int) -> dict[str, Any]:
    samples = await _voice_samples(tenant_id)
    if len(samples) < 5:
        raise RuntimeError("not enough posts to describe this author's voice yet")

    user = "Posts by this author:\n\n" + "\n\n---\n\n".join(samples)
    profile, cost = await complete_json(
        tenant_id=tenant_id,
        purpose="voice",
        system=system_blocks(extraction_prompts.VOICE_SYSTEM),
        user=user,
        schema=schema_of(VoiceProfile),
        effort="high",
        max_tokens=8000,
    )
    if profile is None:
        raise RuntimeError("voice profiling returned no usable result")

    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        tenant.settings = {**(tenant.settings or {}), "voice_profile": profile}
    log.info("voice.built", tenant_id=tenant_id, cost=round(cost, 4))
    return {"profile": profile, "cost_usd": cost}


DRAFT_SYSTEM = """You write a Telegram post for one channel, in that author's own voice.

Ground rules:
- Match the voice profile you are given: length, register, how they open and close, how they use
  emoji and formatting. A post that reads like a generic assistant is a failure.
- Write in the language the author writes in, unless the brief asks for another one.
- Use the earlier posts you are given for facts and for phrasing this channel already uses. Do not
  invent facts, numbers, quotes or dates that are not in the brief or those posts.
- Telegram has no headings and no markdown lists. Use short paragraphs, and bullet characters only
  if this author already does.
- Return the post itself, with no preamble, no title line and no explanation."""


def draft_user_prompt(
    brief: str, voice: dict[str, Any] | None, context: list[dict[str, Any]], language: str | None
) -> str:
    parts = [f"Brief: {brief}"]
    if language:
        parts.append(f"Language: {language}")
    if voice:
        parts.append("Voice profile:\n" + chat_prompts.voice_block(voice))
    if context:
        parts.append(
            "Earlier posts from this channel on the same subject (facts and phrasing to reuse):\n\n"
            + "\n\n---\n\n".join(f"[{c['date']}] {c['text'][:900]}" for c in context)
        )
    parts.append("Write the post now.")
    return "\n\n".join(parts)


async def _context_posts(tenant_id: int, brief: str) -> list[dict[str, Any]]:
    hits = await hybrid.search(tenant_id, brief, limit=CONTEXT_POSTS)
    if not hits:
        return []
    async with session_scope() as db:
        rows = (await db.scalars(select(Post).where(Post.id.in_([h[0] for h in hits])))).all()
        channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
    return [
        {"id": p.tg_message_id, "date": p.date.date().isoformat(), "text": p.text or "", "views": p.views}
        for p in rows
        if channel is not None
    ]


async def draft_post(
    tenant_id: int, brief: str, *, language: str | None = None, length_hint: str | None = None
) -> dict[str, Any]:
    """Draft a post in the blogger's voice. Returns Telegram HTML plus the posts it drew on."""
    from kanalchi.ai.claude import get_client, record_usage
    from kanalchi.core.pricing import Usage, cost_usd
    from kanalchi.core.settings import get_settings

    s = get_settings()
    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        voice = (tenant.settings or {}).get("voice_profile")
        default_language = tenant.primary_lang

    context = await _context_posts(tenant_id, brief)
    user = draft_user_prompt(brief, voice, context, language or default_language)
    if length_hint:
        user += f"\n\nLength: {length_hint}."

    message = await get_client().messages.create(
        model=s.chat_model,
        max_tokens=4000,
        system=system_blocks(DRAFT_SYSTEM),
        messages=[{"role": "user", "content": user}],
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
    )
    usage = Usage.from_response(message.usage)
    usd = await record_usage(tenant_id, s.chat_model, "draft", usage)

    if message.stop_reason == "refusal":
        return {"refused": True, "cost_usd": usd}

    text = next((b.text for b in message.content if b.type == "text"), "").strip()
    html = sanitize(markdown_to_telegram_html(text))
    return {
        "html": html,
        "cost_usd": usd or cost_usd(s.chat_model, usage),
        "context_post_ids": [c["id"] for c in context],
    }


async def suggest_tags(tenant_id: int, html: str) -> list[dict[str, Any]]:
    """Tags a draft would get once published, so the blogger can see where it lands before posting."""
    from kanalchi.ai.mapping import alias_index, dimension_ids
    from kanalchi.telegram.formatting import visible_text
    from kanalchi.text.normalize import normalize

    text = visible_text(html)
    if not text.strip():
        return []
    async with session_scope() as db:
        from kanalchi.core.models import Dimension, Tag

        dims = await dimension_ids(db, tenant_id)
        normalized = normalize(text)
        found: list[dict[str, Any]] = []
        for key, dim_id in dims.items():
            index = await alias_index(db, tenant_id, dim_id)
            for alias_norm, tag_id in index.items():
                if len(alias_norm) > 3 and alias_norm in normalized:
                    tag = await db.get(Tag, tag_id)
                    dimension = await db.get(Dimension, dim_id)
                    if tag is not None and all(f["slug"] != tag.slug for f in found):
                        found.append(
                            {
                                "slug": tag.slug,
                                "name": tag.canonical_name,
                                "labels": tag.labels or {},
                                "dimension": dimension.key if dimension else key,
                                "post_count": tag.post_count,
                            }
                        )
    return found[:12]
