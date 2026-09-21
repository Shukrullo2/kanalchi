"""Channel profile and channel-specific dimension discovery (Opus 5, once per tenant, admin-reviewed)."""

from __future__ import annotations

import random
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from kanalchi.ai import prompts
from kanalchi.ai.claude import complete_json, system_blocks
from kanalchi.ai.schemas import ChannelProfile, schema_of
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, Dimension, Post, Tenant

log = get_logger(__name__)

SAMPLE_SIZE = 400

# Dimensions every channel gets. `programmatic` ones are filled without an LLM.
UNIVERSAL_DIMENSIONS: list[dict[str, Any]] = [
    {
        "key": "themes",
        "kind": "open",
        "labels": {"uz": "Mavzular", "ru": "Темы", "en": "Themes"},
        "sort_order": 10,
        "extraction_hint": "broad reusable topics of the post",
    },
    {
        "key": "people",
        "kind": "open",
        "labels": {"uz": "Shaxslar", "ru": "Люди", "en": "People"},
        "sort_order": 20,
        "extraction_hint": "named individuals",
    },
    {
        "key": "gov_orgs",
        "kind": "open",
        "labels": {"uz": "Davlat idoralari", "ru": "Госорганы", "en": "Government"},
        "sort_order": 30,
        "extraction_hint": "ministries, hokimliks, agencies, courts, state companies",
    },
    {
        "key": "orgs",
        "kind": "open",
        "labels": {"uz": "Tashkilotlar", "ru": "Организации", "en": "Organisations"},
        "sort_order": 40,
        "extraction_hint": "companies, NGOs, universities, banks",
    },
    {
        "key": "products",
        "kind": "open",
        "labels": {"uz": "Mahsulotlar", "ru": "Продукты", "en": "Products"},
        "sort_order": 50,
        "extraction_hint": "products, apps, services, brands",
    },
    {
        "key": "locations",
        "kind": "open",
        "labels": {"uz": "Joylar", "ru": "Места", "en": "Places"},
        "sort_order": 60,
        "extraction_hint": "countries, regions, cities, districts, venues",
    },
    {
        "key": "events",
        "kind": "open",
        "labels": {"uz": "Voqealar", "ru": "События", "en": "Events"},
        "sort_order": 70,
        "extraction_hint": "named events, summits, conflicts, holidays",
    },
    {
        "key": "laws",
        "kind": "open",
        "labels": {"uz": "Hujjatlar", "ru": "Документы", "en": "Laws"},
        "sort_order": 80,
        "extraction_hint": "laws, decrees, regulations, official documents",
    },
    {
        "key": "media_outlets",
        "kind": "open",
        "labels": {"uz": "OAV", "ru": "СМИ", "en": "Media"},
        "sort_order": 90,
        "extraction_hint": "newspapers, TV, news sites, other Telegram channels cited as sources",
    },
    {
        "key": "link_domains",
        "kind": "programmatic",
        "labels": {"uz": "Havolalar", "ru": "Ссылки", "en": "Links"},
        "sort_order": 100,
    },
    {
        "key": "hashtags",
        "kind": "programmatic",
        "labels": {"uz": "Xeshteglar", "ru": "Хештеги", "en": "Hashtags"},
        "sort_order": 110,
    },
    {
        "key": "format",
        "kind": "fixed",
        "labels": {"uz": "Post turi", "ru": "Тип поста", "en": "Format"},
        "sort_order": 120,
    },
    {
        "key": "stance",
        "kind": "fixed",
        "labels": {"uz": "Pozitsiya", "ru": "Позиция", "en": "Stance"},
        "sort_order": 130,
    },
    {
        "key": "language",
        "kind": "programmatic",
        "labels": {"uz": "Til", "ru": "Язык", "en": "Language"},
        "sort_order": 140,
    },
    {
        "key": "media_type",
        "kind": "programmatic",
        "labels": {"uz": "Media", "ru": "Медиа", "en": "Media type"},
        "sort_order": 150,
    },
]


async def ensure_universal_dimensions(tenant_id: int) -> None:
    async with session_scope() as db:
        for d in UNIVERSAL_DIMENSIONS:
            stmt = insert(Dimension).values(
                tenant_id=tenant_id,
                key=d["key"],
                kind=d["kind"],
                labels=d["labels"],
                extraction_hint=d.get("extraction_hint"),
                is_universal=True,
                sort_order=d["sort_order"],
            )
            await db.execute(stmt.on_conflict_do_nothing(constraint="uq_dimensions_tenant_key"))


async def sample_posts(tenant_id: int, n: int = SAMPLE_SIZE) -> list[str]:
    """Stratified-ish sample: newest, most engaging, and a random spread."""
    async with session_scope() as db:
        base = select(Post.text).where(
            Post.tenant_id == tenant_id,
            Post.is_deleted.is_(False),
            Post.is_album_root.is_(True),
            func.length(Post.text) > 40,
        )
        newest = (await db.scalars(base.order_by(Post.date.desc()).limit(n // 4))).all()
        top = (await db.scalars(base.order_by(Post.engagement_score.desc()).limit(n // 4))).all()
        spread = (await db.scalars(base.order_by(func.random()).limit(n))).all()
    seen: set[str] = set()
    out: list[str] = []
    for t in [*newest, *top, *spread]:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    random.Random(7).shuffle(out)
    return out[:n]


async def discover(tenant_id: int) -> dict[str, Any]:
    """Build the channel profile and propose custom dimensions. Stored disabled until an admin approves."""
    await ensure_universal_dimensions(tenant_id)
    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        channel = await db.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
        post_count = await db.scalar(
            select(func.count()).select_from(Post).where(Post.tenant_id == tenant_id)
        )
    samples = await sample_posts(tenant_id)
    if len(samples) < 5:
        raise RuntimeError("not enough posts to profile this channel yet")

    payload = {
        "title": (channel.title if channel else tenant.title),
        "about": channel.about if channel else None,
        "participants_count": channel.participants_count if channel else None,
        "post_count": post_count,
    }
    profile, cost = await complete_json(
        tenant_id=tenant_id,
        purpose="discovery",
        system=system_blocks(prompts.DISCOVERY_SYSTEM),
        user=prompts.discovery_user(payload, samples),
        schema=schema_of(ChannelProfile),
        effort="high",
        max_tokens=16000,
    )
    if profile is None:
        raise RuntimeError("dimension discovery returned no usable result")

    async with session_scope() as db:
        tenant = await db.get(Tenant, tenant_id)
        tenant.settings = {**(tenant.settings or {}), "channel_profile": profile}
        for i, d in enumerate(profile.get("custom_dimensions", [])):
            key = d["key"] if d["key"].startswith("custom_") else f"custom_{d['key']}"
            stmt = insert(Dimension).values(
                tenant_id=tenant_id,
                key=key,
                kind="open",
                labels={"uz": d["label_uz"], "ru": d["label_ru"], "en": d["label_en"]},
                description=d.get("description"),
                extraction_hint=d.get("extraction_hint"),
                is_universal=False,
                is_visible=True,
                sort_order=200 + i,
            )
            await db.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_dimensions_tenant_key",
                    set_={"labels": stmt.excluded.labels, "extraction_hint": stmt.excluded.extraction_hint},
                )
            )
    log.info(
        "discovery.done", tenant_id=tenant_id, dimensions=len(profile.get("custom_dimensions", [])), cost=cost
    )
    return {"profile": profile, "cost_usd": cost}
