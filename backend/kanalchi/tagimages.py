"""A picture for each subject in the index.

Three sources, in descending order of how reliably they are *right*:

1. An organisation's own site icon. Which site is not guessed — the channel links
   out nearly twenty thousand times, so the domain is read off its own posts and
   confirmed by name similarity. `Asakabank` -> `asakabank.uz` is a fact from the
   archive, not an inference.
2. Wikidata, for people and places only. Not for organisations: searching
   "Markaziy bank" returns the generic concept `central bank`, whose picture is
   the US Federal Reserve. A confidently wrong logo is worse than none.
3. Nothing — the card falls back to a post thumbnail, then to initials.

Everything is fetched once and stored in our own bucket. Hotlinking would make
every page load wait on third-party servers and would hand each reader's IP to
whichever sites the channel happens to cite.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import re
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from PIL import Image
from sqlalchemy import text, update

from kanalchi.core import storage
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Tag
from kanalchi.core.settings import get_settings

log = get_logger(__name__)

# Dimensions whose members are organisations with a website.
LOGO_DIMENSIONS = ("gov_orgs", "orgs", "custom_banks", "custom_state_companies", "media_outlets")
# Dimensions Wikidata answers well, because the article *is* about the subject.
WIKIDATA_DIMENSIONS = ("people", "locations")

# Aggregators and social platforms are never a subject's own site.
GENERIC_DOMAINS = {
    "t.me",
    "telegra.ph",
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "facebook.com",
    "x.com",
    "twitter.com",
    "google.com",
    "bit.ly",
    "apple.com",
    "play.google.com",
    "linkedin.com",
    "wikipedia.org",
    "controller.bot",
    "onelink.to",
}
MIN_SIMILARITY = 0.55
MAX_IMAGE_BYTES = 2_000_000
# Below this an icon is a favicon built for a 16px browser tab; blown up to a
# card it is mush, and a blank card reads better than a smear.
MIN_ICON_PX = 32
# What every logo is stored at, so one stylesheet suits all of them.
LOGO_PX = 256
# Mean luminance (0-255) of the ink above which artwork is "light" — drawn in
# white for a dark header, and therefore invisible on a white plate.
LIGHT_INK = 205
UA = {"User-Agent": "Kanalchi/1.0 (channel archive; contact via the channel)"}

# Ordered best-first: a touch icon is made for display, a favicon is made for a tab.
ICON_PATTERNS = (
    re.compile(rb'<link[^>]+rel=["\'][^"\']*apple-touch-icon[^"\']*["\'][^>]*>', re.I),
    re.compile(rb'<link[^>]+rel=["\'][^"\']*icon[^"\']*["\'][^>]*>', re.I),
)
HREF = re.compile(rb'href=["\']([^"\']+)["\']', re.I)


# ----------------------------------------------------------------- domain match
DOMAIN_SQL = text(
    """
WITH org AS (
    SELECT t.id, replace(replace(lower(t.canonical_norm), ' ', ''), '-', '') AS squashed
    FROM tags t WHERE t.id = :tag_id
), cand AS (
    SELECT l.domain, split_part(l.domain, '.', 1) AS label, count(*) AS hits
    FROM post_tags pt
    JOIN post_links l ON l.post_id = pt.post_id
    WHERE pt.tag_id = :tag_id AND l.domain IS NOT NULL
    GROUP BY 1, 2
)
SELECT c.domain, similarity(c.label, o.squashed) AS sim
FROM cand c CROSS JOIN org o
ORDER BY sim DESC, c.hits DESC
LIMIT 1
"""
)


async def domain_for_tag(db, tag_id: int) -> str | None:
    """The organisation's own site, read off the links in its own posts."""
    row = (await db.execute(DOMAIN_SQL, {"tag_id": tag_id})).first()
    if row is None:
        return None
    domain, sim = row[0], float(row[1] or 0)
    if domain in GENERIC_DOMAINS or sim < MIN_SIMILARITY:
        return None
    return domain


# ----------------------------------------------------------------- fetching
async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        response = await client.get(url, headers=UA, follow_redirects=True, timeout=12)
    except Exception as exc:  # noqa: BLE001
        log.debug("tagimage.fetch_failed", url=url[:120], error=str(exc)[:120])
        return None
    if response.status_code == 429:
        # Worth naming: Wikidata throttles by IP and stays throttled for a while,
        # so a run that silently stores no portraits is usually this, not absence.
        log.warning("tagimage.rate_limited", url=url[:80])
        return None
    return response if response.status_code == 200 and response.content else None


def normalise_icon(data: bytes) -> tuple[bytes, bool] | None:
    """Re-draw a fetched icon as one predictable PNG, or reject it.

    Three things go wrong with icons taken off the open web, and all three are
    fixed here rather than in the stylesheet:

    * `.ico` is a container of several sizes, and some are malformed enough that
      browsers decline to draw them at all (tbcbank.uz declares a negative
      width). Pillow reads them, so we pick the largest frame and re-encode.
    * Sizes run from 16px to 512px, which no single layout can flatter.
    * Many are white artwork meant for a dark site header. On a white plate they
      vanish, which is why the second return value reports the ink's tone and
      lets the card choose a plate the logo can actually be seen against.
    """
    try:
        image = Image.open(io.BytesIO(data))
        sizes = image.ico.sizes() if image.format == "ICO" else {image.size}
        best = max(sizes, key=lambda wh: wh[0] * wh[1])
        if image.format == "ICO":
            image.size = best
        image = image.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        log.debug("tagimage.undecodable", error=str(exc)[:120])
        return None

    if max(image.size) < MIN_ICON_PX:
        return None
    # Read the buffer directly: `getdata()` is deprecated in new Pillow and
    # `get_flattened_data()` does not exist in the old one, but `tobytes()` has
    # meant the same four bytes per RGBA pixel throughout.
    raw = image.tobytes()
    total, count = 0.0, 0
    for i in range(0, len(raw), 4):
        if raw[i + 3] > 40:
            total += 0.299 * raw[i] + 0.587 * raw[i + 1] + 0.114 * raw[i + 2]
            count += 1
    if not count:
        return None
    luminance = total / count

    image.thumbnail((LOGO_PX, LOGO_PX), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), luminance >= LIGHT_INK


async def site_icon(client: httpx.AsyncClient, domain: str) -> tuple[bytes, bool] | None:
    """The best usable icon a site offers: its touch icon, else its favicon.

    Returns the normalised PNG and whether its ink is light. A candidate that
    cannot be decoded or is too small does not end the search — the next one is
    tried, so a broken `.ico` still falls through to `/apple-touch-icon.png`.
    """
    page = await _get(client, f"https://{domain}/")
    candidates: list[str] = []
    if page is not None:
        for pattern in ICON_PATTERNS:
            for tag in pattern.findall(page.content[:200_000]):
                href = HREF.search(tag)
                if href:
                    candidates.append(urljoin(str(page.url), href.group(1).decode("utf-8", "ignore")))
    candidates.append(f"https://{domain}/apple-touch-icon.png")
    candidates.append(f"https://{domain}/favicon.ico")

    for url in candidates:
        response = await _get(client, url)
        if response is None or len(response.content) > MAX_IMAGE_BYTES:
            continue
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        if not (content_type.startswith("image/") or url.endswith((".png", ".ico", ".svg", ".jpg"))):
            continue
        normalised = normalise_icon(response.content)
        if normalised is not None:
            return normalised
    return None


async def wikidata_image(client: httpx.AsyncClient, name: str) -> tuple[bytes, str] | None:
    """A portrait from Wikidata — people and places only, where the article is the subject."""
    search = await _get(
        client,
        "https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&limit=1"
        f"&language=en&uselang=en&search={quote(name)}",
    )
    if search is None:
        return None
    try:
        hits = search.json().get("search") or []
    except Exception:  # noqa: BLE001
        return None
    if not hits:
        return None

    claims = await _get(
        client,
        f"https://www.wikidata.org/w/api.php?action=wbgetclaims&format=json&entity={hits[0]['id']}",
    )
    if claims is None:
        return None
    try:
        data = claims.json().get("claims", {})
    except Exception:  # noqa: BLE001
        return None
    filename = None
    for prop in ("P18", "P154"):
        if prop in data:
            try:
                filename = data[prop][0]["mainsnak"]["datavalue"]["value"]
                break
            except Exception:  # noqa: BLE001, PERF203
                continue
    if not filename:
        return None

    # Commons stores files under a path derived from the md5 of the name.
    safe = filename.replace(" ", "_")
    digest = hashlib.md5(safe.encode()).hexdigest()  # noqa: S324 — Commons' own scheme, not security
    url = (
        f"https://upload.wikimedia.org/wikipedia/commons/thumb/{digest[0]}/{digest[:2]}/"
        f"{quote(safe)}/320px-{quote(safe)}"
    )
    response = await _get(client, url)
    if response is None or len(response.content) > MAX_IMAGE_BYTES:
        return None
    return response.content, response.headers.get("content-type", "image/jpeg").split(";")[0]


# ----------------------------------------------------------------- the job
EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/svg+xml": "svg",
    "image/webp": "webp",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
    "image/gif": "gif",
}

PENDING_SQL = text(
    """
SELECT t.id, t.canonical_name, d.key
FROM tags t JOIN dimensions d ON d.id = t.dimension_id
WHERE t.tenant_id = :tenant_id AND t.status = 'active' AND t.post_count > 0
  AND t.image_key IS NULL AND d.key = ANY(:dimensions)
ORDER BY t.post_count DESC
LIMIT :limit
"""
)


async def fetch_images(tenant_id: int, limit: int = 500, concurrency: int = 6) -> dict[str, Any]:
    """Find and store a picture for every subject that can have one."""
    s = get_settings()
    async with session_scope() as db:
        rows = (
            await db.execute(
                PENDING_SQL,
                {
                    "tenant_id": tenant_id,
                    "dimensions": list(LOGO_DIMENSIONS + WIKIDATA_DIMENSIONS),
                    "limit": limit,
                },
            )
        ).all()
    if not rows:
        return {"checked": 0, "stored": 0}

    gate = asyncio.Semaphore(concurrency)
    # Wikidata answers 429 to anything resembling a burst, so it gets a queue of
    # one with a pause between calls, regardless of the wider concurrency.
    wikidata_gate = asyncio.Semaphore(1)
    stored = {"logo": 0, "logo_light": 0, "wikidata": 0}

    async with httpx.AsyncClient() as client:

        async def one(tag_id: int, name: str, dim_key: str) -> None:
            async with gate:
                data = b""
                content_type = "image/png"
                source = ""
                if dim_key in LOGO_DIMENSIONS:
                    async with session_scope() as db:
                        domain = await domain_for_tag(db, tag_id)
                    if not domain:
                        return
                    icon = await site_icon(client, domain)
                    if icon is None:
                        return
                    data, light = icon
                    # The tone travels with the row because only the card knows
                    # what it will draw the logo on top of.
                    source = "logo_light" if light else "logo"
                elif dim_key in WIKIDATA_DIMENSIONS:
                    async with wikidata_gate:
                        portrait = await wikidata_image(client, name)
                        await asyncio.sleep(1.5)
                    if portrait is None:
                        return
                    data, content_type = portrait
                    source = "wikidata"
                if not data:
                    return
                key = f"tags/{tenant_id}/{tag_id}.{EXT.get(content_type, 'png')}"
                await storage.upload_bytes(s.s3_bucket_media, key, data, content_type)
                async with session_scope() as db:
                    await db.execute(
                        update(Tag).where(Tag.id == tag_id).values(image_key=key, image_source=source)
                    )
                stored[source] += 1

        await asyncio.gather(*(one(*row) for row in rows), return_exceptions=True)

    log.info("tagimage.done", tenant_id=tenant_id, checked=len(rows), **stored)
    return {"checked": len(rows), **stored}
