import hashlib
import hmac
import time

from kanalchi.api.auth import verify_telegram_login


def _sign(payload: dict, token: str) -> dict:
    data = {k: v for k, v in payload.items() if v is not None}
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hashlib.sha256(token.encode()).digest()
    return {**payload, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()}


def test_valid_login():
    token = "123456:ABC-DEF"
    payload = _sign({"id": 42, "first_name": "Ali", "username": None, "auth_date": int(time.time())}, token)
    assert verify_telegram_login(payload, token)


def test_tampered_login():
    token = "123456:ABC-DEF"
    payload = _sign({"id": 42, "first_name": "Ali", "auth_date": int(time.time())}, token)
    payload["id"] = 43
    assert not verify_telegram_login(payload, token)


def test_expired_login():
    token = "123456:ABC-DEF"
    payload = _sign({"id": 42, "auth_date": int(time.time()) - 90000}, token)
    assert not verify_telegram_login(payload, token)
