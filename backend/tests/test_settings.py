"""Settings must accept the values infra/.env.example ships with."""

import pytest

from kanalchi.core.settings import Settings


@pytest.mark.parametrize(("raw", "expected"), [("", []), ("123", [123]), ("1, 2;3", [1, 2, 3])])
def test_admin_tg_ids_parse_from_env(monkeypatch, raw, expected):
    monkeypatch.setenv("ADMIN_TG_IDS", raw)
    assert Settings(_env_file=None).admin_tg_ids == expected


@pytest.mark.parametrize(
    ("raw", "expected"), [("", []), ("video", ["video"]), ("Video, audio", ["video", "audio"])]
)
def test_media_skip_kinds_parse_from_env(monkeypatch, raw, expected):
    monkeypatch.setenv("MEDIA_SKIP_KINDS", raw)
    assert Settings(_env_file=None).media_skip_kinds == expected
