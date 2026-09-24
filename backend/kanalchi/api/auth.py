"""Telegram Login Widget verification and Redis-backed sessions."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import asdict, dataclass
from typing import Any

from itsdangerous import BadSignature, URLSafeSerializer

from kanalchi.core.redis import get_redis
from kanalchi.core.settings import get_settings

SESSION_COOKIE = "sid"


def verify_telegram_login(data: dict[str, Any], bot_token: str, max_age_s: int = 86400) -> bool:
    """Validate the payload the Telegram Login Widget posts (https://core.telegram.org/widgets/login)."""
    payload = {k: v for k, v in data.items() if k != "hash" and v is not None and v != ""}
    received = str(data.get("hash", ""))
    check_string = "\n".join(f"{k}={payload[k]}" for k in sorted(payload))
    secret = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return False
    try:
        auth_date = int(payload.get("auth_date", 0))
    except (TypeError, ValueError):
        return False
    return (time.time() - auth_date) < max_age_s


@dataclass(slots=True)
class SessionData:
    user_id: int
    tg_user_id: int
    role: str  # admin | owner | editor | user (signed up on the platform domain)
    tenant_id: int | None
    name: str
    username: str | None = None
    photo_url: str | None = None


def _signer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().session_secret, salt="kanalchi-session")


async def create_session(data: SessionData) -> str:
    sid = secrets.token_urlsafe(32)
    ttl = get_settings().session_ttl_days * 86400
    await get_redis().set(f"sess:{sid}", json.dumps(asdict(data)), ex=ttl)
    return _signer().dumps(sid)


async def load_session(cookie_value: str | None) -> SessionData | None:
    if not cookie_value:
        return None
    try:
        sid = _signer().loads(cookie_value)
    except BadSignature:
        return None
    raw = await get_redis().get(f"sess:{sid}")
    if not raw:
        return None
    return SessionData(**json.loads(raw))


async def destroy_session(cookie_value: str | None) -> None:
    if not cookie_value:
        return
    try:
        sid = _signer().loads(cookie_value)
    except BadSignature:
        return
    await get_redis().delete(f"sess:{sid}")
