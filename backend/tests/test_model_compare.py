"""The model comparison has to catch the failure that matters.

A cheaper model will almost always return schema-valid JSON, so validity proves
nothing. Script drift turns out not to be the risk either — `normalize()` folds
Cyrillic onto Latin, so a model that echoes "Марказий банк" still reaches the
right tag. What normalization cannot repair is an entity that was never found,
one that was invented, an unexpanded abbreviation, or a ministry filed as a
person. These tests pin the scorer to those.
"""

from __future__ import annotations

from kanalchi.ai.compare import _score
from kanalchi.ai.extraction import _request

SYSTEM = [{"type": "text", "text": "system"}]
POST = {"id": 1, "text": "Марказий банк ставкани оширди", "date": "2026-01-01"}


def _result(entities: list[tuple], themes: list[str], **rest):
    return {
        "entities": [
            {"surface": e[0], "normalized": e[1], "type": e[2] if len(e) > 2 else "org"} for e in entities
        ],
        "themes": [{"name": t, "confidence": 0.9} for t in themes],
        "format": rest.get("format", "news"),
        "language_primary": rest.get("language_primary", "uz-Cyrl"),
        "is_low_content": rest.get("is_low_content", False),
    }


def test_script_drift_is_forgiven_because_normalize_handles_it():
    """Echoing the Cyrillic surface is harmless: it folds onto the same tag."""
    baseline = _result([("Марказий банк", "Markaziy bank")], ["iqtisodiyot"])
    echoed = _result([("Марказий банк", "Марказий банк")], ["iqtisodiyot"])
    assert _score(baseline, echoed)["entity_recall"] == 1.0


def test_an_unexpanded_abbreviation_is_a_miss():
    """`normalize()` cannot turn CBU into the bank's name — only the model can."""
    baseline = _result([("CBU", "Markaziy bank")], [])
    lazy = _result([("CBU", "CBU")], [])
    score = _score(baseline, lazy)
    assert score["entity_recall"] == 0.0
    assert score["missed"] == ["markaziy bank"]


def test_a_missed_entity_is_not_masked_by_agreeing_themes():
    baseline = _result([("Тошкент", "Toshkent"), ("Adliya vazirligi", "Adliya vazirligi")], ["qonunchilik"])
    partial = _result([("Тошкент", "Toshkent")], ["qonunchilik"])
    score = _score(baseline, partial)
    assert score["entity_recall"] == 0.5
    assert score["theme_overlap"] == 1.0, "themes agreeing must not hide the missing entity"


def test_a_ministry_filed_as_a_person_is_caught():
    baseline = _result([("Adliya vazirligi", "Adliya vazirligi", "gov_org")], [])
    mistyped = _result([("Adliya vazirligi", "Adliya vazirligi", "person")], [])
    score = _score(baseline, mistyped)
    assert score["entity_recall"] == 1.0, "the name was found"
    assert score["type_agreement"] == 0.0, "but filed under the wrong kind"


def test_a_faithful_model_scores_well():
    baseline = _result([("Марказий банк", "Markaziy bank")], ["iqtisodiyot"])
    good = _result([("CBU", "Markaziy bank")], ["iqtisodiyot"])
    score = _score(baseline, good)
    assert score["entity_recall"] == 1.0
    assert score["entity_precision"] == 1.0
    assert score["type_agreement"] == 1.0
    assert score["format_agrees"] and score["language_agrees"]


def test_invented_entities_show_up_as_lost_precision():
    baseline = _result([("Тошкент", "Toshkent")], [])
    noisy = _result([("Тошкент", "Toshkent"), ("?", "Some Invented Body")], [])
    score = _score(baseline, noisy)
    assert score["entity_recall"] == 1.0
    assert score["entity_precision"] == 0.5
    assert score["invented"] == ["some invented body"]


def test_disagreement_on_the_cheap_fields_is_visible():
    score = _score(
        _result([], [], format="news", language_primary="uz-Cyrl"),
        _result([], [], format="opinion", language_primary="ru"),
    )
    assert score["format_agrees"] is False
    assert score["language_agrees"] is False


def test_both_models_see_the_same_prompt_and_schema():
    """Only the model and its thinking settings may differ, or the comparison is meaningless."""
    sonnet = _request(POST, SYSTEM, "claude-sonnet-5")["params"]
    haiku = _request(POST, SYSTEM, "claude-haiku-4-5")["params"]
    assert sonnet["system"] == haiku["system"]
    assert sonnet["messages"] == haiku["messages"]
    assert sonnet["output_config"]["format"] == haiku["output_config"]["format"]


def test_haiku_gets_a_request_it_can_accept():
    """Haiku 4.5 rejects output_config.effort and adaptive thinking."""
    haiku = _request(POST, SYSTEM, "claude-haiku-4-5")["params"]
    assert "effort" not in haiku["output_config"]
    assert haiku["thinking"] == {"type": "disabled"}

    sonnet = _request(POST, SYSTEM, "claude-sonnet-5")["params"]
    assert sonnet["output_config"]["effort"] == "low"
    assert sonnet["thinking"] == {"type": "adaptive"}
