"""Chunking + embedding of posts."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select, update

from kanalchi.ai.embeddings import embed
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, Extraction, Post, PostChunk
from kanalchi.core.settings import get_settings
from kanalchi.text.chunk import approx_tokens, split_post, synthetic_chunk

log = get_logger(__name__)

MIN_CHARS = 15


def is_low_content(text: str, media_kind: str) -> bool:
    """Stickers, bare emoji and one-word posts carry no retrievable signal."""
    stripped = (text or "").strip()
    if len(stripped) >= MIN_CHARS:
        return False
    return media_kind in {"none", "sticker"} or not stripped


async def rebuild_chunks(post_ids: list[int]) -> int:
    """Re-chunk and embed the given posts, including the synthetic Latin chunk when an extraction exists."""
    if not post_ids:
        return 0
    s = get_settings()
    async with session_scope() as db:
        rows = (
            await db.execute(
                select(Post, Channel.title, Extraction.result)
                .join(Channel, Channel.id == Post.channel_id)
                .outerjoin(Extraction, (Extraction.post_id == Post.id) & (Extraction.status == "succeeded"))
                .where(Post.id.in_(post_ids), Post.is_deleted.is_(False))
            )
        ).all()

    payload: list[tuple[int, int, int, str, str]] = []  # post_id, tenant_id, position, text, embed_text
    skipped: list[int] = []
    for post, channel_title, extraction in rows:
        if not post.is_album_root or is_low_content(post.text, post.media_kind):
            skipped.append(post.id)
            continue
        prefix = f"{channel_title} · {post.date:%Y-%m-%d}\n"
        for i, chunk in enumerate(split_post(post.text)):
            payload.append((post.id, post.tenant_id, i, chunk, prefix + chunk))
        if extraction:
            synth = synthetic_chunk(extraction)
            if synth:
                payload.append((post.id, post.tenant_id, -1, synth, prefix + synth))

    if skipped:
        async with session_scope() as db:
            await db.execute(update(Post).where(Post.id.in_(skipped)).values(index_status="skipped"))
    if not payload:
        return 0

    tenant_id = payload[0][1]
    vectors, _ = await embed([p[4] for p in payload], input_type="document", tenant_id=tenant_id)

    touched = sorted({p[0] for p in payload})
    async with session_scope() as db:
        await db.execute(delete(PostChunk).where(PostChunk.post_id.in_(touched)))
        now = datetime.now(UTC)
        for (post_id, tid, position, text, _), vector in zip(payload, vectors, strict=True):
            db.add(
                PostChunk(
                    tenant_id=tid,
                    post_id=post_id,
                    position=position,
                    text=text,
                    token_count=approx_tokens(text),
                    embedding=vector,
                    embed_model=s.embed_model,
                    embedded_at=now,
                )
            )
        # Only ever advances. This runs twice per post: once on the first pass, and
        # again after extraction to add the synthetic Latin chunk — and that second
        # call must not drag a `tagged` post back to `embedded`, which is an earlier
        # stage and made 5,000 finished posts look unindexed.
        await db.execute(
            update(Post)
            .where(Post.id.in_(touched), Post.index_status.in_(["pending", "embedded"]))
            .values(index_status="embedded")
        )
    log.info("index.embedded", posts=len(touched), chunks=len(payload))
    return len(payload)


async def pending_embed_ids(tenant_id: int, limit: int = 500) -> list[int]:
    async with session_scope() as db:
        return list(
            (
                await db.scalars(
                    select(Post.id)
                    .where(
                        Post.tenant_id == tenant_id,
                        Post.is_deleted.is_(False),
                        Post.is_album_root.is_(True),
                        Post.index_status == "pending",
                    )
                    .order_by(Post.date.desc())
                    .limit(limit)
                )
            ).all()
        )
