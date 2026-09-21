"""Encryption at rest for Telethon sessions and bot tokens (MultiFernet with rotation support)."""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet

from kanalchi.core.settings import get_settings


class CryptoNotConfigured(RuntimeError):
    pass


@lru_cache
def _fernet() -> MultiFernet:
    s = get_settings()
    if not s.app_master_key:
        if s.is_dev:
            # Deterministic dev key so restarts keep working; never used in prod (settings validation below).
            return MultiFernet([Fernet(b"ZGV2LW9ubHktZGV2LW9ubHktZGV2LW9ubHktZGV2MDE=")])
        raise CryptoNotConfigured("APP_MASTER_KEY is not set")
    keys = [Fernet(s.app_master_key.encode())]
    if s.app_master_key_prev:
        keys.append(Fernet(s.app_master_key_prev.encode()))
    return MultiFernet(keys)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def rotate(token: str) -> str:
    """Re-encrypt a token with the primary key (used by `kanalchi rotate-keys`)."""
    return _fernet().rotate(token.encode()).decode()


def generate_key() -> str:
    return Fernet.generate_key().decode()
