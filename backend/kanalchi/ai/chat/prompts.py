"""Chat system prompt assembly.

The prompt is ordered most-stable-first so the cache breakpoint on the last block covers everything:
instructions, then the channel profile, then the taxonomy digest. Volatile facts (today's date, the
reader's locale, a budget warning) are appended as a mid-conversation system message instead, which
leaves the cached prefix untouched.
"""

from __future__ import annotations

import json
from typing import Any

CITATION_TOKEN = "[[post:{id}]]"

VIEWER_ROLE = """You answer questions about one Telegram channel, using only what that channel has published.

How you work:
- Search before you answer. Never rely on memory or outside knowledge about the subject.
- Every factual statement about the channel carries a citation marker `[[post:ID]]`, where ID is a
  post_id returned by a tool in THIS conversation. Put the marker right after the statement it supports.
- Never write a citation for an id a tool did not return. If you did not find it, say so plainly.
- If the archive does not answer the question, say what the channel does cover instead. Do not speculate.
- Quote the channel's own wording for anything contentious, rather than paraphrasing it into your voice.

How you write:
- Answer in the language the reader used. The channel may be in a different language; translate
  what you report, but keep names as the channel writes them.
- Lead with the answer. Keep it short: a few sentences, or a short list when the reader asked for several things.
- Dates matter in a news archive. Say when something was posted when it affects the answer.
- No preamble, no meta-commentary about your search process, no offers of further help."""

RESEARCH_ROLE = """You are the research assistant of the person who writes this Telegram channel.

You are talking to the author, not to a reader. They use you to remember what they have already
published, to find gaps, and to develop ideas for the next post.

How you work:
- Search before you answer; their archive is the source of truth, not your memory.
- Cite with `[[post:ID]]` using ids tools returned in THIS conversation, so they can reopen their own posts.
- Be direct about gaps: what they have not covered, what has gone quiet, where an earlier claim
  now looks dated. That is the value you add.
- When they ask for an idea or a draft, ground it in specific earlier posts and say which ones.

How you write:
- Answer in the language they used.
- Be concise and concrete. They know their own channel: no need to re-explain its subject to them."""


def channel_block(profile: dict[str, Any] | None, stats: dict[str, Any] | None) -> str:
    if not profile and not stats:
        return ""
    payload = {
        "profile": {
            k: profile.get(k)
            for k in (
                "title",
                "one_liner",
                "topics",
                "audience",
                "formality",
                "language_mix",
                "posting_style",
            )
        }
        if profile
        else None,
        "archive": stats,
    }
    return "About this channel:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def taxonomy_block(summary: str) -> str:
    if not summary or summary == "{}":
        return ""
    return (
        "Tags available for filtering, by dimension (name [slug] (post count)). This is the top of each "
        "dimension only; call list_tags for the rest:\n" + summary
    )


def voice_block(voice: dict[str, Any] | None) -> str:
    if not voice:
        return ""
    return "How this author writes (use it when drafting):\n" + json.dumps(
        voice, ensure_ascii=False, sort_keys=True
    )


def turn_context(*, today: str, locale: str, budget_note: str | None = None) -> str:
    """Volatile per-turn facts. Goes in a mid-conversation system message, never the cached prefix."""
    parts = [f"Today is {today}.", f"The reader is using the interface in '{locale}'."]
    if budget_note:
        parts.append(budget_note)
    return " ".join(parts)
