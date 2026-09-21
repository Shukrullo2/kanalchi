"""Draft HTML <-> Telegram entities.

Drafts are stored as the Telegram HTML subset because that is what the Bot API accepts directly and
what the editor can round-trip losslessly. This module validates that HTML (a draft comes from a
browser, so it is untrusted) and measures it the way Telegram does, in UTF-16 code units.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Exactly what Telegram's HTML parse mode understands. Anything else is dropped.
ALLOWED_TAGS = {
    "b",
    "strong",
    "i",
    "em",
    "u",
    "ins",
    "s",
    "strike",
    "del",
    "span",
    "tg-spoiler",
    "a",
    "code",
    "pre",
    "blockquote",
    "br",
}
ALLOWED_ATTRS = {"a": {"href"}, "span": {"class"}, "code": {"class"}, "blockquote": {"expandable"}}
SAFE_SCHEMES = ("http://", "https://", "tg://", "mailto:", "tel:")

TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024
MEDIA_GROUP_LIMIT = 10

_TAG_RE = re.compile(r"<[^>]+>")
_ENTITY_RE = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|\w+);")


class DraftValidationError(ValueError):
    pass


class _Sanitizer(HTMLParser):
    """Keeps the tags Telegram supports, drops the rest, and never emits unbalanced markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.out.append("\n")
            return
        if tag not in ALLOWED_TAGS:
            return
        allowed = ALLOWED_ATTRS.get(tag, set())
        kept: list[str] = []
        for name, value in attrs:
            if name not in allowed or value is None:
                continue
            if name == "href":
                if not value.lower().startswith(SAFE_SCHEMES):
                    return  # a link we cannot vouch for: drop the anchor, keep its text
                kept.append(f'href="{_escape_attr(value)}"')
            elif name == "class" and value in {"tg-spoiler", "language-python", "language-sql"}:
                kept.append(f'class="{_escape_attr(value)}"')
            elif name == "expandable":
                kept.append("expandable")
        self.out.append(f"<{tag}{' ' + ' '.join(kept) if kept else ''}>")
        self.open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "br" or tag not in ALLOWED_TAGS:
            return
        if tag in self.open_tags:
            # close anything opened inside it first, so the result is always balanced
            while self.open_tags:
                current = self.open_tags.pop()
                self.out.append(f"</{current}>")
                if current == tag:
                    break

    def handle_data(self, data: str) -> None:
        self.out.append(data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    def handle_entityref(self, name: str) -> None:
        self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.out.append(f"&#{name};")

    def result(self) -> str:
        tail = "".join(f"</{t}>" for t in reversed(self.open_tags))
        return "".join(self.out) + tail


def _escape_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def sanitize(html: str) -> str:
    """Strip a draft down to the markup Telegram accepts. Input comes from a browser, so never trust it."""
    parser = _Sanitizer()
    parser.feed(html or "")
    parser.close()
    return parser.result()


def visible_text(html: str) -> str:
    """The text a reader sees, which is what Telegram's length limits apply to."""
    without_tags = _TAG_RE.sub("", html or "")
    return (
        without_tags.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&amp;", "&")
    )


def length(html: str) -> int:
    """Telegram counts UTF-16 code units, so an emoji costs two and a Cyrillic letter costs one."""
    return len(visible_text(html).encode("utf-16-le")) // 2


def validate(html: str, *, has_media: bool, media_count: int = 0) -> str:
    """Sanitize and length-check a draft. Returns the cleaned HTML or raises with a readable reason."""
    cleaned = sanitize(html)
    text = visible_text(cleaned).strip()
    if not text and not has_media:
        raise DraftValidationError("a post needs text or media")
    limit = CAPTION_LIMIT if has_media else TEXT_LIMIT
    size = length(cleaned)
    if size > limit:
        what = "caption" if has_media else "post"
        raise DraftValidationError(f"the {what} is {size} characters, Telegram allows {limit}")
    if media_count > MEDIA_GROUP_LIMIT:
        raise DraftValidationError(f"Telegram allows at most {MEDIA_GROUP_LIMIT} items in one album")
    return cleaned


def markdown_to_telegram_html(text: str) -> str:
    """Convert the light markdown a model tends to produce into Telegram's HTML subset.

    Deliberately small: Telegram has no headings and no lists, so those become plain lines rather
    than being silently dropped or rendered as literal asterisks.
    """
    out = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    out = re.sub(r"```(?:\w+)?\n(.*?)```", lambda m: f"<pre>{m.group(1).rstrip()}</pre>", out, flags=re.S)
    out = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', out)
    out = re.sub(r"(?<!\*)\*\*([^*\n]+)\*\*(?!\*)", r"<b>\1</b>", out)
    out = re.sub(r"(?<!_)__([^_\n]+)__(?!_)", r"<b>\1</b>", out)
    out = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<i>\1</i>", out)
    out = re.sub(r"(?<![_\w])_([^_\n]+)_(?![_\w])", r"<i>\1</i>", out)
    out = re.sub(r"~~([^~\n]+)~~", r"<s>\1</s>", out)
    out = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", out, flags=re.M)
    out = re.sub(r"^\s*[-*+]\s+(.+)$", r"• \1", out, flags=re.M)
    return out.strip()
