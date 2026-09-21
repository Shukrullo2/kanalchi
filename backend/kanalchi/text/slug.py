from __future__ import annotations

import re

from kanalchi.text.normalize import normalize

_DASHES = re.compile(r"[\s_]+")


def slugify(text: str, max_len: int = 80) -> str:
    base = _DASHES.sub("-", normalize(text)).strip("-")
    return (base[:max_len].rstrip("-")) or "tag"
