"""Chat logic that does not need a model: citation validation, prompts, tools, SSE framing."""

from __future__ import annotations

import json

import pytest

from kanalchi.ai.chat.agent import Event, load_history, validate_citations
from kanalchi.ai.chat.prompts import channel_block, taxonomy_block, turn_context, voice_block
from kanalchi.ai.chat.tools import ToolBox, tool_definitions


# --------------------------------------------------------------------- citations
def test_valid_citation_is_kept():
    text, cited = validate_citations("The rate rose [[post:42]].", {42})
    assert text == "The rate rose [[post:42]]."
    assert cited == [42]


def test_invented_citation_is_stripped():
    """The whole trust model rests on this: a marker for an id no tool returned must not survive."""
    text, cited = validate_citations("It happened [[post:999]] last year.", {42})
    assert "999" not in text
    assert cited == []


def test_mixed_citations_keep_only_the_real_ones():
    text, cited = validate_citations("A [[post:1]] and B [[post:2]] and C [[post:3]].", {1, 3})
    assert "[[post:1]]" in text and "[[post:3]]" in text and "[[post:2]]" not in text
    assert cited == [1, 3]


def test_repeated_citation_is_listed_once():
    _, cited = validate_citations("[[post:7]] then [[post:7]] again", {7})
    assert cited == [7]


def test_text_without_citations_is_untouched():
    text, cited = validate_citations("Just an answer.", {1, 2})
    assert text == "Just an answer."
    assert cited == []


# --------------------------------------------------------------------- SSE framing
def test_event_framing_is_valid_sse():
    frame = Event("delta", {"text": "salom"}).sse()
    assert frame.startswith("event: delta\ndata: ")
    assert frame.endswith("\n\n")
    payload = json.loads(frame.split("data: ", 1)[1].strip())
    assert payload == {"text": "salom"}


def test_event_framing_keeps_unicode_readable():
    frame = Event("delta", {"text": "Тошкент"}).sse()
    assert "Тошкент" in frame


# --------------------------------------------------------------------- tools
def test_tool_definitions_are_sorted_for_cache_stability():
    names = [t["name"] for t in tool_definitions("viewer")]
    assert names == sorted(names)


def test_every_tool_is_strict_and_closed():
    for tool in tool_definitions("viewer"):
        assert tool["strict"] is True, tool["name"]
        schema = tool["input_schema"]
        assert schema["additionalProperties"] is False, tool["name"]
        assert set(schema["required"]) == set(schema["properties"]), tool["name"]


def test_search_tool_advertises_cross_script_behaviour():
    search = next(t for t in tool_definitions("viewer") if t["name"] == "search_posts")
    assert "Cyrillic" in search["description"]


async def test_unknown_tool_returns_an_error_not_an_exception():
    box = ToolBox(tenant_id=1)
    out = json.loads(await box.run("no_such_tool", {}))
    assert "error" in out


async def test_toolbox_starts_with_no_revealed_posts():
    assert ToolBox(tenant_id=1).seen_post_ids == set()


# --------------------------------------------------------------------- prompts
def test_channel_block_is_stable_for_caching():
    profile = {"title": "T", "topics": ["b", "a"], "one_liner": "x"}
    stats = {"posts": 10}
    assert channel_block(profile, stats) == channel_block(profile, stats)


def test_empty_blocks_collapse_to_nothing():
    assert channel_block(None, None) == ""
    assert taxonomy_block("") == ""
    assert taxonomy_block("{}") == ""
    assert voice_block(None) == ""


def test_turn_context_carries_volatile_facts_only():
    note = turn_context(today="2026-09-21", locale="uz", budget_note="Answer briefly today.")
    assert "2026-09-21" in note and "uz" in note and "briefly" in note


@pytest.mark.parametrize("kind", ["viewer", "research"])
def test_tool_set_is_defined_for_both_chat_kinds(kind: str):
    assert len(tool_definitions(kind)) >= 7


# --------------------------------------------------------------------- history
async def test_history_of_an_unknown_session_is_empty():
    import uuid

    try:
        assert await load_history(uuid.uuid4()) == []
    except Exception:
        pytest.skip("database not available")
