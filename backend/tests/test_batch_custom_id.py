"""The batch `custom_id` is the only thing tying a result back to its post, and the
API rejects the whole batch if any id breaks its character rules."""

from __future__ import annotations

import re

from kanalchi.ai.extraction import EXTRACTOR_VERSION, custom_id, parse_custom_id

# Verbatim from the Anthropic Message Batches API error for a bad custom_id.
BATCH_CUSTOM_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def test_custom_id_is_accepted_by_the_batches_api():
    for post_id in (1, 12345, 2**40):
        assert BATCH_CUSTOM_ID.match(custom_id(post_id)), custom_id(post_id)


def test_custom_id_round_trips():
    for post_id in (1, 12345, 2**40):
        assert parse_custom_id(custom_id(post_id)) == post_id


def test_custom_id_carries_the_extractor_version():
    assert str(EXTRACTOR_VERSION) in custom_id(7)


def test_parse_rejects_garbage():
    assert parse_custom_id("") is None
    assert parse_custom_id("x-1-abc") is None
    assert parse_custom_id("nothing") is None
