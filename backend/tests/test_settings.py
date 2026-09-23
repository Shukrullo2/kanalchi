"""Settings must accept the values infra/.env.example ships with."""

import pytest

from kanalchi.core.settings import Settings


@pytest.mark.parametrize(("raw", "expected"), [("", []), ("123", [123]), ("1, 2;3", [1, 2, 3])])
def test_admin_tg_ids_parse_from_env(monkeypatch, raw, expected):
    monkeypatch.setenv("ADMIN_TG_IDS", raw)
    assert Settings(_env_file=None).admin_tg_ids == expected
