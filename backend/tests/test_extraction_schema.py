"""The extraction schema is the contract between the model, the database and the taxonomy."""

import json

from kanalchi.ai.mapping import extraction_values
from kanalchi.ai.prompts import extraction_system, extraction_user
from kanalchi.ai.schemas import (
    ChannelProfile,
    PostExtraction,
    TagMappingBatch,
    TaxonomyProposal,
    VoiceProfile,
    schema_of,
)

MODELS = [PostExtraction, TaxonomyProposal, ChannelProfile, VoiceProfile, TagMappingBatch]


def test_schemas_are_inlined_for_structured_outputs():
    for model in MODELS:
        blob = json.dumps(schema_of(model))
        assert "$ref" not in blob, model.__name__
        assert "$defs" not in blob, model.__name__


def test_schemas_forbid_extra_properties():
    for model in MODELS:
        schema = schema_of(model)
        assert schema["additionalProperties"] is False, model.__name__


def test_every_field_is_required():
    # Structured outputs need every property listed in `required`; optionality is expressed as `| None`.
    for model in MODELS:
        schema = schema_of(model)
        assert set(schema["required"]) == set(schema["properties"]), model.__name__


def test_nested_objects_also_forbid_extras():
    schema = schema_of(PostExtraction)
    entities = schema["properties"]["entities"]["items"]
    assert entities["additionalProperties"] is False
    assert set(entities["required"]) == set(entities["properties"])


def test_extraction_validates_a_realistic_payload():
    payload = {
        "language_primary": "uz-Latn",
        "format": "news",
        "title": "Toshkentda yangi loyiha",
        "summary": "Hokimlik yangi qurilish loyihasini e'lon qildi.",
        "themes": [{"name": "Qurilish", "confidence": 0.9}],
        "entities": [
            {
                "type": "gov_org",
                "surface": "Тошкент шаҳар ҳокимлиги",
                "normalized": "Toshkent shahar hokimligi",
                "lang": "uz-Cyrl",
                "role": "subject",
                "sentiment_toward": "neutral",
                "confidence": 0.95,
            }
        ],
        "custom": [{"dimension": "custom_districts", "values": ["Chilonzor"]}],
        "links": [{"url": "https://gazeta.uz", "kind": "news", "described_as": None}],
        "sentiment": "neutral",
        "stance": None,
        "key_claims": ["Loyiha e'lon qilindi"],
        "is_ad": False,
        "has_call_to_action": False,
        "is_low_content": False,
        "hashtags": ["toshkent"],
        "taxonomy_mapped": ["toshkent"],
        "new_candidates": ["Chilonzor tumani"],
    }
    parsed = PostExtraction.model_validate(payload)
    assert parsed.entities[0].normalized == "Toshkent shahar hokimligi"


def test_extraction_values_maps_entity_types_to_dimensions():
    data = {
        "entities": [
            {"type": "person", "normalized": "Ali Valiyev", "surface": "Ali", "lang": "uz-Latn"},
            {"type": "gov_org", "normalized": "Adliya vazirligi", "surface": "Минюст", "lang": "ru"},
            {"type": "unknown_type", "normalized": "Skipped", "surface": "x", "lang": "en"},
        ],
        "themes": [{"name": "Qonunchilik"}],
        "custom": [{"dimension": "custom_courts", "values": ["Oliy sud"]}],
    }
    values = extraction_values(data)
    dims = {v[0] for v in values}
    assert dims == {"people", "gov_orgs", "themes", "custom_courts"}
    assert ("gov_orgs", "Adliya vazirligi", "Минюст", "ru") in values


def test_extraction_prompt_includes_custom_dimensions_and_rules():
    system = extraction_system(
        {"title": "Test", "one_liner": "A channel", "topics": ["law"]},
        [{"key": "custom_courts", "extraction_hint": "courts mentioned"}],
    )
    assert "custom_courts" in system
    assert "courts mentioned" in system
    assert "Toshkent" in system  # normalization examples must survive prompt assembly


def test_extraction_prompt_is_stable_for_caching():
    profile = {"title": "Test", "topics": ["a", "b"]}
    dims = [{"key": "custom_x", "extraction_hint": "hint"}]
    assert extraction_system(profile, dims) == extraction_system(profile, dims)


def test_extraction_user_includes_context_header():
    user = extraction_user(
        {
            "channel_title": "Kanal",
            "date": "2026-01-01",
            "media_kind": "photo",
            "links": ["https://a.uz"],
            "text": "Salom",
        }
    )
    assert "channel: Kanal" in user and "media: photo" in user and "https://a.uz" in user
    assert user.endswith("Salom")
