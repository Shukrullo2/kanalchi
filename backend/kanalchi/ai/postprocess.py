"""Turn one stored extraction into tags on the post.

Programmatic dimensions (format, stance, language, media type, hashtags, link domains) are written
directly. Open dimensions go through the alias -> embedding -> pending cascade in `mapping`; the LLM
step is deliberately deferred to a batch rather than run per post.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from kanalchi.ai.mapping import (
    SIM_ASSIGN,
    alias_index,
    assign,
    dimension_ids,
    extraction_values,
    nearest_tags,
    record_candidate,
)
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Dimension, Post, PostLink, PostTag, Tag
from kanalchi.text.normalize import normalize
from kanalchi.text.slug import slugify

log = get_logger(__name__)

# Fixed value sets rendered as tags without an LLM.
FORMAT_LABELS = {
    "news": {"uz": "Yangilik", "ru": "Новость", "en": "News"},
    "announcement": {"uz": "E'lon", "ru": "Объявление", "en": "Announcement"},
    "opinion": {"uz": "Fikr", "ru": "Мнение", "en": "Opinion"},
    "analysis": {"uz": "Tahlil", "ru": "Аналитика", "en": "Analysis"},
    "explainer": {"uz": "Tushuntirish", "ru": "Разбор", "en": "Explainer"},
    "ad": {"uz": "Reklama", "ru": "Реклама", "en": "Ad"},
    "poll": {"uz": "So'rovnoma", "ru": "Опрос", "en": "Poll"},
    "repost": {"uz": "Repost", "ru": "Репост", "en": "Repost"},
    "quote": {"uz": "Iqtibos", "ru": "Цитата", "en": "Quote"},
    "personal": {"uz": "Shaxsiy", "ru": "Личное", "en": "Personal"},
    "qa": {"uz": "Savol-javob", "ru": "Вопрос-ответ", "en": "Q&A"},
    "giveaway": {"uz": "Sovrin", "ru": "Розыгрыш", "en": "Giveaway"},
    "event_invite": {"uz": "Tadbir", "ru": "Приглашение", "en": "Event"},
    "meme": {"uz": "Mem", "ru": "Мем", "en": "Meme"},
    "other": {"uz": "Boshqa", "ru": "Другое", "en": "Other"},
}
STANCE_LABELS = {
    "supportive": {"uz": "Qo'llab-quvvatlovchi", "ru": "Поддерживающая", "en": "Supportive"},
    "critical": {"uz": "Tanqidiy", "ru": "Критическая", "en": "Critical"},
    "neutral": {"uz": "Neytral", "ru": "Нейтральная", "en": "Neutral"},
    "ambivalent": {"uz": "Aralash", "ru": "Смешанная", "en": "Mixed"},
}
LANGUAGE_LABELS = {
    "uz-Latn": {"uz": "O'zbekcha (lotin)", "ru": "Узбекский (латиница)", "en": "Uzbek (Latin)"},
    "uz-Cyrl": {"uz": "O'zbekcha (kirill)", "ru": "Узбекский (кириллица)", "en": "Uzbek (Cyrillic)"},
    "ru": {"uz": "Ruscha", "ru": "Русский", "en": "Russian"},
    "en": {"uz": "Inglizcha", "ru": "Английский", "en": "English"},
    "mixed": {"uz": "Aralash", "ru": "Смешанный", "en": "Mixed"},
    "other": {"uz": "Boshqa", "ru": "Другой", "en": "Other"},
}
MEDIA_LABELS = {
    "none": {"uz": "Matn", "ru": "Текст", "en": "Text"},
    "photo": {"uz": "Rasm", "ru": "Фото", "en": "Photo"},
    "album": {"uz": "Albom", "ru": "Альбом", "en": "Album"},
    "video": {"uz": "Video", "ru": "Видео", "en": "Video"},
    "document": {"uz": "Hujjat", "ru": "Документ", "en": "Document"},
    "audio": {"uz": "Audio", "ru": "Аудио", "en": "Audio"},
    "voice": {"uz": "Ovozli", "ru": "Голосовое", "en": "Voice"},
    "sticker": {"uz": "Stiker", "ru": "Стикер", "en": "Sticker"},
    "animation": {"uz": "GIF", "ru": "GIF", "en": "GIF"},
    "poll": {"uz": "So'rovnoma", "ru": "Опрос", "en": "Poll"},
}


async def ensure_tag(
    db,
    tenant_id: int,
    dimension_id: int,
    canonical_name: str,
    *,
    labels: dict[str, str] | None = None,
    source: str = "programmatic",
) -> int:
    """Get-or-create a tag by canonical name within a dimension. Returns the tag id."""
    norm = normalize(canonical_name)[:200]
    existing = await db.scalar(
        select(Tag.id).where(
            Tag.tenant_id == tenant_id, Tag.dimension_id == dimension_id, Tag.canonical_norm == norm
        )
    )
    if existing:
        return existing
    base = slugify(canonical_name)
    slug = base
    for suffix in range(1, 40):
        clash = await db.scalar(select(Tag.id).where(Tag.tenant_id == tenant_id, Tag.slug == slug))
        if not clash:
            break
        slug = f"{base}-{suffix}"
    stmt = (
        insert(Tag)
        .values(
            tenant_id=tenant_id,
            dimension_id=dimension_id,
            slug=slug,
            canonical_name=canonical_name[:200],
            canonical_norm=norm,
            labels=labels or {},
            status="active",
            source=source,
        )
        .on_conflict_do_nothing(constraint="uq_tags_tenant_dim_norm")
        .returning(Tag.id)
    )
    tag_id = await db.scalar(stmt)
    if tag_id is None:
        tag_id = await db.scalar(
            select(Tag.id).where(
                Tag.tenant_id == tenant_id, Tag.dimension_id == dimension_id, Tag.canonical_norm == norm
            )
        )
    return tag_id


async def apply_extraction(post_id: int, data: dict[str, Any]) -> dict[str, int]:
    """Write all tags for one post. Idempotent: existing auto-assigned tags are replaced."""
    stats = {"programmatic": 0, "alias": 0, "embedding": 0, "pending": 0}
    async with session_scope() as db:
        post = await db.get(Post, post_id)
        if post is None:
            return stats
        tenant_id = post.tenant_id
        dims = await dimension_ids(db, tenant_id)

        # Replace previous machine assignments; manual ones are kept.
        await db.execute(delete(PostTag).where(PostTag.post_id == post_id, PostTag.source != "manual"))

        # --- programmatic dimensions -------------------------------------------------
        async def put(dim_key: str, value: str | None, labels: dict[str, dict[str, str]]) -> None:
            nonlocal stats
            if not value or dim_key not in dims:
                return
            tag_id = await ensure_tag(db, tenant_id, dims[dim_key], value, labels=labels.get(value, {}))
            if tag_id:
                await assign(db, tenant_id, post_id, tag_id, source="programmatic")
                stats["programmatic"] += 1

        await put("format", data.get("format"), FORMAT_LABELS)
        await put("stance", data.get("stance"), STANCE_LABELS)
        await put("language", data.get("language_primary"), LANGUAGE_LABELS)
        await put("media_type", post.media_kind, MEDIA_LABELS)

        if "hashtags" in dims:
            for tag in dict.fromkeys(data.get("hashtags") or []):
                clean = tag.lstrip("#").strip()
                if clean:
                    tid = await ensure_tag(db, tenant_id, dims["hashtags"], f"#{clean}")
                    if tid:
                        await assign(db, tenant_id, post_id, tid, source="programmatic")
                        stats["programmatic"] += 1

        if "link_domains" in dims:
            domains = (
                await db.scalars(
                    select(PostLink.domain).where(PostLink.post_id == post_id, PostLink.domain != "")
                )
            ).all()
            for domain in dict.fromkeys(domains):
                tid = await ensure_tag(db, tenant_id, dims["link_domains"], domain)
                if tid:
                    await assign(db, tenant_id, post_id, tid, source="programmatic")
                    stats["programmatic"] += 1

        # --- slugs the model picked from the taxonomy we gave it ----------------------
        slugs = [s for s in (data.get("taxonomy_mapped") or []) if s]
        if slugs:
            mapped = (
                await db.execute(
                    select(Tag.id).where(
                        Tag.tenant_id == tenant_id, Tag.slug.in_(slugs), Tag.status == "active"
                    )
                )
            ).all()
            for (tag_id,) in mapped:
                await assign(db, tenant_id, post_id, tag_id, source="extractor")
                stats["alias"] += 1

        # --- open dimensions: alias match, then embedding, then pending ---------------
        values = extraction_values(data)
        by_dim: dict[str, list[tuple[str, str, str | None]]] = {}
        for dim_key, name, surface, lang in values:
            if dim_key in dims:
                by_dim.setdefault(dim_key, []).append((name, surface, lang))

        unmatched: list[tuple[int, str, str, str | None]] = []  # dimension_id, name, surface, lang
        for dim_key, items in by_dim.items():
            dim_id = dims[dim_key]
            index = await alias_index(db, tenant_id, dim_id)
            for name, surface, lang in items:
                tag_id = index.get(normalize(name))
                if tag_id:
                    await assign(
                        db, tenant_id, post_id, tag_id, source="alias", evidence={"surface": surface}
                    )
                    stats["alias"] += 1
                else:
                    unmatched.append((dim_id, name, surface, lang))

    # Embedding pass runs outside the transaction: it may call Voyage.
    if unmatched:
        from kanalchi.ai.embeddings import embed

        vectors, _ = await embed([n for _, n, _, _ in unmatched], input_type="query", tenant_id=tenant_id)
        async with session_scope() as db:
            for (dim_id, name, surface, lang), vector in zip(unmatched, vectors, strict=True):
                near = await nearest_tags(db, tenant_id, dim_id, vector, limit=1)
                if near and near[0][2] >= SIM_ASSIGN:
                    await assign(
                        db,
                        tenant_id,
                        post_id,
                        near[0][0],
                        source="embedding",
                        confidence=round(near[0][2], 3),
                        evidence={"surface": surface, "matched": near[0][1]},
                    )
                    stats["embedding"] += 1
                else:
                    await record_candidate(
                        db, tenant_id, dim_id, name, post_id=post_id, surface=surface, lang=lang
                    )
                    stats["pending"] += 1

    async with session_scope() as db:
        post = await db.get(Post, post_id)
        if post is not None:
            post.index_status = "tagged"
    return stats


async def visible_dimensions(tenant_id: int) -> list[Dimension]:
    async with session_scope() as db:
        return list(
            (
                await db.scalars(
                    select(Dimension)
                    .where(Dimension.tenant_id == tenant_id, Dimension.is_visible.is_(True))
                    .order_by(Dimension.sort_order)
                )
            ).all()
        )
