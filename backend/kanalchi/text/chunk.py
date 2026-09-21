"""Chunking for embeddings. Telegram posts are short, so most become a single chunk."""

from __future__ import annotations

import re

MAX_CHARS = 1500
TARGET = 1200
HARD = 1600

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def approx_tokens(text: str) -> int:
    """Rough token estimate; used for accounting only, never for truncation decisions."""
    return max(1, len(text) // 3)


def _split_sentences(paragraph: str) -> list[str]:
    out: list[str] = []
    buf = ""
    for piece in _SENTENCE_END.split(paragraph):
        candidate = f"{buf} {piece}".strip()
        if len(candidate) > HARD and buf:
            out.append(buf)
            buf = piece
        else:
            buf = candidate
    if buf:
        out.append(buf)
    return out


def split_post(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= MAX_CHARS:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        candidate = f"{buf}\n\n{p}" if buf else p
        if len(candidate) <= TARGET:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        if len(p) > TARGET:
            chunks.extend(_split_sentences(p))
        else:
            buf = p
    if buf:
        chunks.append(buf)

    # One-paragraph overlap keeps a thought that straddles a boundary retrievable from both sides.
    overlapped: list[str] = []
    for i, c in enumerate(chunks):
        if i == 0:
            overlapped.append(c)
            continue
        tail = chunks[i - 1].split("\n\n")[-1]
        overlapped.append(f"{tail}\n\n{c}" if len(tail) + len(c) < HARD else c)
    return overlapped


def synthetic_chunk(extraction: dict) -> str:
    """Latin-script digest built from the extraction, so Cyrillic posts answer Latin queries.

    Stored at position -1 in `post_chunks`. It carries the title, key claims and every normalized
    entity and theme name, which is what entity-centric queries actually look for.
    """
    parts: list[str] = []
    if extraction.get("title"):
        parts.append(extraction["title"])
    for claim in (extraction.get("key_claims") or [])[:3]:
        parts.append(claim)
    names = [e.get("normalized", "") for e in (extraction.get("entities") or [])]
    names += [t.get("name", "") for t in (extraction.get("themes") or [])]
    for custom in extraction.get("custom") or []:
        names += list(custom.get("values") or [])
    names = [n for n in dict.fromkeys(names) if n]
    if names:
        parts.append(" · ".join(names))
    return "\n".join(p for p in parts if p).strip()
