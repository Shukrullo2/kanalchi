"""A public channel's size as Telegram's own web preview (t.me/s/<username>) shows it.

Plain HTTP, no MTProto session, so the API can run it inline while a visitor waits. Channel
message ids count up from 1, so the newest post's id is the size of the archive plus whatever
was deleted along the way (about 3% over for the first real channel): a safe upper bound for a
price. The page also carries the title, the subscriber count and the text of the latest posts,
which is enough to measure how long the channel's posts are.
"""

from __future__ import annotations

import html
import re

import httpx

from kanalchi.core.logging import get_logger

log = get_logger(__name__)

PAGES = 3  # ~20 posts a page
TIMEOUT = 8.0

_POST = re.compile(r'data-post="[^"/]+/(\d+)"')
_TEXT = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
_TITLE = re.compile(r'<meta property="og:title" content="([^"]*)"')
_COUNTER = re.compile(
    r'<span class="counter_value">([^<]+)</span>\s*<span class="counter_type">(subscribers?|members?)</span>'
)
_TAG = re.compile(r"<[^>]+>")


def parse_count(text: str) -> int | None:
    """'60.3K' → 60300, '1.2M' → 1200000, '812' → 812."""
    text = text.strip().replace(" ", "").replace(",", "")
    mult = {"K": 1_000, "M": 1_000_000}.get(text[-1:].upper(), 1)
    try:
        return int(round(float(text[:-1] if mult > 1 else text) * mult))
    except ValueError:
        return None


def parse_page(page: str) -> dict:
    """Post ids and their text lengths (0 for a post without text) from one t.me/s page."""
    posts: dict[int, int] = {}
    # Each message starts with its data-post attribute; its text sits between it and the next.
    chunks = _POST.split(page)
    for i in range(1, len(chunks) - 1, 2):
        body = chunks[i + 1]
        m = _TEXT.search(body)
        text = html.unescape(_TAG.sub("", m.group(1).replace("<br/>", "\n"))) if m else ""
        posts[int(chunks[i])] = len(text.strip())
    title = _TITLE.search(page)
    counter = _COUNTER.search(page)
    return {
        "posts": posts,
        "title": html.unescape(title.group(1)) if title else "",
        "participants_count": parse_count(counter.group(1)) if counter else None,
    }


async def fetch_web_preview(username: str) -> dict | None:
    """{title, participants_count, total, avg_chars, text_share}, or None when the channel has
    no public web preview (not a channel, private, or Telegram hides it)."""
    posts: dict[int, int] = {}
    head: dict = {}
    url = f"https://t.me/s/{username}"
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 (osor.uz)"}
        ) as http:
            for n in range(PAGES):
                resp = await http.get(url, params={"before": min(posts)} if posts else None)
                if resp.status_code != 200:
                    break  # a redirect to t.me/<username> means there is no web preview
                page = parse_page(resp.text)
                if n == 0:
                    head = page
                fresh = {k: v for k, v in page["posts"].items() if k not in posts}
                if not fresh:
                    break
                posts.update(fresh)
    except httpx.HTTPError as exc:
        log.info("webpreview.failed", username=username, error=str(exc)[:200])
        if not posts:
            return None
    if not posts:
        return None
    lengths = list(posts.values())
    with_text = [n for n in lengths if n > 0]
    return {
        "title": head.get("title", ""),
        "participants_count": head.get("participants_count"),
        "total": max(posts),
        "avg_chars": sum(with_text) / len(with_text) if with_text else None,
        "text_share": len(with_text) / len(lengths),
    }
