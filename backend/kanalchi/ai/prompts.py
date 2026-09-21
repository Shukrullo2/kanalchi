"""Prompt text. Kept in one module so the cached prefixes are byte-stable and reviewable."""

from __future__ import annotations

import json
from typing import Any

NORMALIZATION_RULES = """Normalization rules (they make the same entity collide across scripts):
- `normalized` is always Latin script, full official form, Title Case.
- Uzbek Cyrillic and Russian spellings map to the Uzbek Latin canonical form:
  Тошкент / Toshkent / Ташкент -> "Toshkent"; Ўзбекистон / Узбекистан -> "O'zbekiston".
- Government bodies get their full official name, not an abbreviation:
  "hokimlik" -> "Toshkent shahar hokimligi"; "Минюст" -> "Adliya vazirligi".
- People are "Firstname Lastname" in Latin script. Keep the conventional spelling of
  well-known Russian and international names (Vladimir Putin, Elon Musk).
- Companies and products keep their own branding ("Uzum Market", "Payme", "Telegram").
- `surface` is the exact wording from the post, untouched.
- Do not invent entities. If the post only alludes to someone without naming them, skip it."""

EXTRACTION_ROLE = """You label posts from one Telegram channel so that a public web archive of that
channel can be browsed by tag and searched. You return one JSON object per post and nothing else.

Be precise and conservative:
- Only record what the post actually says. Never infer facts from outside knowledge.
- `title` and `summary` are written in the language of the post, not translated.
- `themes` are broad reusable topics (2-3 max), not restatements of the headline.
- `key_claims` are at most 3 short factual statements the post asserts.
- `is_low_content` is true for stickers, bare emoji, pure greetings, and posts under ~15 characters.
- `is_ad` is true for paid promotion, sponsored placements and giveaways run for a third party."""


def dimension_list(dimensions: list[dict[str, Any]]) -> str:
    lines = []
    for d in dimensions:
        hint = d.get("extraction_hint") or d.get("description") or ""
        lines.append(f"- {d['key']}: {hint}")
    return "\n".join(lines)


def extraction_system(channel_profile: dict[str, Any] | None, custom_dimensions: list[dict[str, Any]]) -> str:
    """Stable prefix for extraction. Changes here invalidate the batch prompt cache, so keep it rare."""
    parts = [EXTRACTION_ROLE, "", NORMALIZATION_RULES]
    if channel_profile:
        parts += [
            "",
            "About this channel:",
            json.dumps(
                {
                    k: channel_profile.get(k)
                    for k in (
                        "title",
                        "one_liner",
                        "topics",
                        "audience",
                        "formality",
                        "language_mix",
                        "posting_style",
                    )
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ]
    if custom_dimensions:
        parts += [
            "",
            "This channel has extra dimensions. Fill `custom` with one entry per dimension that applies,",
            "using the dimension key verbatim and leaving out dimensions the post says nothing about:",
            dimension_list(custom_dimensions),
        ]
    parts += [
        "",
        "Entity types: person, gov_org (state bodies, ministries, hokimliks, agencies), org (companies, NGOs,",
        "universities), product, location, event, law (laws, decrees, regulations), media_outlet, tg_channel, other.",
        "",
        "Post formats: news, announcement, opinion, analysis, explainer, ad, poll, repost, quote, personal, qa,",
        "giveaway, event_invite, meme, other.",
    ]
    return "\n".join(parts)


def taxonomy_section(dimension_key: str, tags: list[dict[str, Any]]) -> str:
    """Existing canonical tags injected into incremental extraction so posts map directly."""
    if not tags:
        return ""
    listed = "; ".join(f"{t['canonical_name']} [{t['slug']}]" for t in tags)
    return f"{dimension_key}: {listed}"


def extraction_user(post: dict[str, Any]) -> str:
    head = [
        f"channel: {post.get('channel_title', '')}",
        f"date: {post.get('date', '')}",
        f"media: {post.get('media_kind', 'none')}",
    ]
    if post.get("links"):
        head.append("links: " + ", ".join(post["links"][:10]))
    if post.get("forward_from"):
        head.append(f"forwarded from: {post['forward_from']}")
    return "\n".join(head) + "\n---\n" + (post.get("text") or "")


DISCOVERY_SYSTEM = """You are setting up a searchable web archive for one Telegram channel.

You are given a representative sample of its posts. Describe the channel, then design 3 to 8 EXTRA tag
dimensions that fit this specific channel and would genuinely help a reader browse it.

The archive already has these universal dimensions, so never duplicate them:
themes, people, gov_orgs, orgs, products, locations, events, laws, media_outlets, link_domains,
hashtags, format, stance, language, media_type, dates.

A good extra dimension is:
- specific to what this channel is about (a food channel -> dishes, restaurants; a legal channel ->
  case types, courts; a crypto channel -> tokens, exchanges),
- something many posts have a value for,
- a short noun phrase, not a sentiment or a quality judgement.

Keys are snake_case and start with `custom_`. Labels are written in Uzbek, Russian and English."""


def discovery_user(channel: dict[str, Any], samples: list[str]) -> str:
    head = [
        f"title: {channel.get('title', '')}",
        f"about: {channel.get('about') or '-'}",
        f"subscribers: {channel.get('participants_count') or '-'}",
        f"posts in archive: {channel.get('post_count', 0)}",
        "",
        f"Sample of {len(samples)} posts:",
    ]
    body = "\n\n---\n\n".join(s[:600] for s in samples)
    return "\n".join(head) + "\n\n" + body


TAXONOMY_SYSTEM = """You turn raw extracted values from one Telegram channel into a clean, canonical tag list
for one dimension of its public archive.

You receive candidates with their frequency and the surface forms they appeared as. Your job:
1. Merge every spelling, script and language variant of the same thing into ONE tag. Uzbek Latin,
   Uzbek Cyrillic and Russian forms of one entity are the same tag.
2. Choose a canonical name (Latin script, full official form) and list EVERY variant in `aliases`,
   including the Cyrillic and Russian spellings, common abbreviations and the surface forms given.
3. Drop noise: typos already merged elsewhere, one-off mentions with no lasting meaning, values that
   are not really members of this dimension.
4. Set `parent_canonical` only where a real hierarchy exists (ministry -> agency, country -> region -> city,
   broad theme -> narrow theme). Otherwise null.

Rules you must obey:
- Existing tags are given with their aliases. Keep their canonical names EXACTLY as given, never split
  an existing tag, and add new aliases to them instead of creating a near-duplicate.
- `merged_candidates` must list the candidate names you folded into each tag, spelled as they were given.
- Every candidate must appear exactly once across `merged_candidates` and `dropped_candidates`.
- Labels: uz is Uzbek Latin, ru is Russian, en is English. Use the conventional local name, not a literal translation."""


def taxonomy_user(
    dimension: str,
    description: str,
    candidates: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    already_proposed: list[str],
    channel_profile: dict[str, Any] | None,
) -> str:
    parts = [f"dimension: {dimension}", f"meaning: {description}"]
    if channel_profile:
        parts.append(f"channel: {channel_profile.get('one_liner', '')}")
    if existing:
        parts += [
            "",
            "Existing tags (keep their canonical names, extend their aliases):",
            "\n".join(
                f"- {t['canonical_name']} | aliases: {', '.join(t.get('aliases', []))}"
                for t in existing[:400]
            ),
        ]
    if already_proposed:
        parts += [
            "",
            "Tags you already proposed for this dimension in earlier chunks (merge into them, do not duplicate):",
            ", ".join(already_proposed[:400]),
        ]
    parts += [
        "",
        f"Candidates ({len(candidates)}), as `name | count | surface forms`:",
        "\n".join(
            f"- {c['name']} | {c['count']} | {', '.join(c.get('surface_forms', [])[:6])}" for c in candidates
        ),
    ]
    return "\n".join(parts)


MAPPING_SYSTEM = """You match newly extracted values to an existing tag list for one dimension of a
Telegram channel archive.

For each candidate, return the canonical name of the tag it is the same thing as, or null when it is
genuinely something new. Different scripts or spellings of one entity are the same thing. Being related
is not enough: only map a candidate when it IS that tag."""


def mapping_user(dimension: str, items: list[dict[str, Any]]) -> str:
    lines = [f"dimension: {dimension}", ""]
    for it in items:
        lines.append(f"candidate: {it['candidate']}")
        if it.get("snippets"):
            lines.append("  seen in: " + " / ".join(s[:120] for s in it["snippets"][:2]))
        lines.append("  nearest tags: " + ", ".join(it.get("nearest", [])))
    return "\n".join(lines)


VOICE_SYSTEM = """You describe how one Telegram blogger writes, so an assistant can draft posts in their voice.

Be concrete and observational. Quote their actual habits: how they open, how they close, which emoji they
use and how often, how long posts run, how they format (bold leads, bullet lists, links at the end),
which words recur. `donts` are things they visibly never do. Excerpts are verbatim from the samples."""
