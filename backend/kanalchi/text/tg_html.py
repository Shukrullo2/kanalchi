"""Telegram MessageEntity[] (UTF-16 offsets) → safe HTML for the web blog, and URL extraction.

Entities are the JSON dicts Telethon produces via `to_dict()` (`{"_": "MessageEntityBold", "offset": 0, "length": 5, ...}`).
The renderer splits the text at every entity boundary and wraps each segment with all entities active there, which yields
valid nesting even for overlapping entities.
"""

from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote

_SIMPLE = {
    "MessageEntityBold": ("<strong>", "</strong>"),
    "MessageEntityItalic": ("<em>", "</em>"),
    "MessageEntityUnderline": ("<u>", "</u>"),
    "MessageEntityStrike": ("<s>", "</s>"),
    "MessageEntitySpoiler": ('<span class="tg-spoiler">', "</span>"),
    "MessageEntityCode": ("<code>", "</code>"),
    "MessageEntityBlockquote": ("<blockquote>", "</blockquote>"),
    "MessageEntityBotCommand": ("<code>", "</code>"),
    "MessageEntityCashtag": ('<span class="tg-cashtag">', "</span>"),
    "MessageEntityBankCard": ('<span class="tg-card">', "</span>"),
    "MessageEntityMentionName": ('<span class="tg-mention">', "</span>"),
    "MessageEntityCustomEmoji": ("", ""),
}
_ATTR = ' rel="nofollow noopener" target="_blank"'


def _u16(text: str) -> bytes:
    return text.encode("utf-16-le")


def _slice(b: bytes, start: int, end: int) -> str:
    return b[start * 2 : end * 2].decode("utf-16-le", errors="ignore")


def _safe_url(url: str) -> str:
    u = (url or "").strip()
    low = u.lower()
    if low.startswith(("http://", "https://", "tg://", "mailto:", "tel:")):
        return html.escape(u, quote=True)
    if low.startswith("//") or ":" in low.split("/")[0]:
        return "#"
    return html.escape("https://" + u, quote=True)


def _open_close(ent: dict[str, Any], b: bytes) -> tuple[str, str]:
    kind = ent.get("_", "")
    if kind in _SIMPLE:
        return _SIMPLE[kind]
    full = _slice(b, ent["offset"], ent["offset"] + ent["length"])
    if kind == "MessageEntityTextUrl":
        return f'<a href="{_safe_url(ent.get("url", ""))}"{_ATTR}>', "</a>"
    if kind == "MessageEntityUrl":
        return f'<a href="{_safe_url(full)}"{_ATTR}>', "</a>"
    if kind == "MessageEntityEmail":
        return f'<a href="mailto:{html.escape(full, quote=True)}">', "</a>"
    if kind == "MessageEntityPhone":
        return f'<a href="tel:{html.escape(full, quote=True)}">', "</a>"
    if kind == "MessageEntityMention":
        return f'<a href="https://t.me/{html.escape(full.lstrip("@"), quote=True)}"{_ATTR}>', "</a>"
    if kind == "MessageEntityHashtag":
        return f'<a href="/search?q={quote(full)}" class="tg-hashtag">', "</a>"
    if kind == "MessageEntityPre":
        lang = html.escape(str(ent.get("language") or ""), quote=True)
        return (f'<pre data-lang="{lang}">' if lang else "<pre>"), "</pre>"
    return "", ""


def entities_to_html(text: str, entities: list[dict[str, Any]] | None) -> str:
    if not text:
        return ""
    b = _u16(text)
    n = len(b) // 2
    ents = [
        e
        for e in (entities or [])
        if isinstance(e, dict) and e.get("length", 0) > 0 and 0 <= e.get("offset", -1) < n
    ]
    if not ents:
        return html.escape(text)
    bounds = {0, n}
    for e in ents:
        bounds.add(e["offset"])
        bounds.add(min(n, e["offset"] + e["length"]))
    points = sorted(bounds)
    ents.sort(key=lambda e: (e["offset"], -e["length"]))
    tags = [(e, *_open_close(e, b)) for e in ents]
    out: list[str] = []
    for a, z in zip(points, points[1:], strict=False):
        active = [t for t in tags if t[0]["offset"] <= a and a < t[0]["offset"] + t[0]["length"]]
        seg = html.escape(_slice(b, a, z))
        out.append("".join(t[1] for t in active) + seg + "".join(t[2] for t in reversed(active)))
    return "".join(out)


def extract_urls(text: str, entities: list[dict[str, Any]] | None) -> list[str]:
    if not text:
        return []
    b = _u16(text)
    urls: list[str] = []
    for e in entities or []:
        kind = e.get("_")
        if kind == "MessageEntityTextUrl" and e.get("url"):
            urls.append(e["url"])
        elif kind == "MessageEntityUrl":
            u = _slice(b, e["offset"], e["offset"] + e["length"]).strip()
            if u and not u.lower().startswith(("http://", "https://")):
                u = "https://" + u
            urls.append(u)
    seen: set[str] = set()
    return [u for u in urls if not (u in seen or seen.add(u))]  # type: ignore[func-returns-value]


def html_to_text(fragment: str) -> str:
    """Crude tag stripper for previews/OG descriptions."""
    import re

    return html.unescape(re.sub(r"<[^>]+>", "", fragment))
