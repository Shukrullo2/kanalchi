"""Text normalization for search and entity matching across Uzbek (Latin/Cyrillic), Russian and English.

`normalize()` produces a lowercase, Latin-script, diacritic-free form used for `text_norm`, `alias_norm`,
`canonical_norm` and query normalization. It is deliberately lossy: its job is to make the same entity written in
different scripts collide, not to be a faithful transliteration.
"""

from __future__ import annotations

import re
import unicodedata

# Uzbek Cyrillic → Latin (official 1995 alphabet, plus apostrophe letters folded to plain letters).
_UZ_CYR = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "j",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "x",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sh",
    "ъ": "",
    "ы": "i",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "ў": "o",
    "қ": "q",
    "ғ": "g",
    "ҳ": "h",
}
# Russian-specific letters not in the Uzbek table are covered above (щ, ы, ъ, ь, э); "х" → "x" matches Uzbek Latin usage.

_MULTI = str.maketrans(_UZ_CYR)

_APOSTROPHES = "ʼ'’ʻ`´‘"
_NON_ALNUM = re.compile(r"[^a-z0-9\s]+")
_WS = re.compile(r"\s+")


def translit(text: str) -> str:
    """Cyrillic → Latin for Uzbek/Russian text; Latin text passes through."""
    lowered = text.lower()
    return lowered.translate(_MULTI)


def strip_diacritics(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize(text: str | None) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    for a in _APOSTROPHES:
        t = t.replace(a, "")  # O'zbekiston → Ozbekiston, G'afur → Gafur
    t = translit(t)
    t = strip_diacritics(t)
    t = t.replace("ʻ", "").replace("ʼ", "")
    t = _NON_ALNUM.sub(" ", t)
    t = _WS.sub(" ", t).strip()
    return t


def detect_script(text: str) -> str:
    """Rough script hint: 'cyrl' | 'latn' | 'mixed' | 'none'."""
    cyr = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    lat = sum(1 for c in text if ("a" <= c.lower() <= "z"))
    if cyr and lat:
        return "mixed" if min(cyr, lat) / max(cyr, lat) > 0.2 else ("cyrl" if cyr > lat else "latn")
    if cyr:
        return "cyrl"
    if lat:
        return "latn"
    return "none"
