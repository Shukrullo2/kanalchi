"""The client-side throttle that lets a rate-limited Voyage account finish a backfill.

These limits are a hard error rather than a queue, so the batching and the pacing
are the difference between a run that completes overnight and one that fails on
every request.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from kanalchi.ai.embeddings import _batches, _Pacer


def test_batches_are_unlimited_without_a_ceiling():
    texts = ["x" * 1000] * 300
    groups = _batches(texts, [400] * 300, 0)
    assert [len(g) for g in groups] == [128, 128, 44]


def test_batches_split_on_the_token_ceiling():
    counts = [400] * 10
    groups = _batches(["x"] * 10, counts, 1000)
    # 400 + 400 = 800 fits, a third would be 1200 and does not.
    assert [len(g) for g in groups] == [2, 2, 2, 2, 2]


def test_a_text_larger_than_the_ceiling_still_goes_out_alone():
    groups = _batches(["a", "b"], [5000, 10], 1000)
    assert groups == [[0], [1]]


def test_batches_preserve_order_and_cover_every_text():
    counts = [300, 900, 100, 700, 50]
    groups = _batches(["a", "b", "c", "d", "e"], counts, 1000)
    assert [i for g in groups for i in g] == [0, 1, 2, 3, 4]


def test_pacer_is_inert_when_unconfigured():
    pacer = _Pacer(0, 0)
    assert pacer.enabled is False
    asyncio.run(pacer.wait(10_000_000))  # returns immediately


def test_pacer_spaces_requests_rather_than_bursting():
    """Three a minute has to mean one every twenty seconds.

    Sending three at once satisfies a naive count-per-window and is exactly what
    the API rejected, so the interval is what this asserts.
    """
    pacer = _Pacer(rpm=60, tpm=0)  # 60/min => one per second
    assert pacer.min_interval == pytest.approx(1.0)

    async def three() -> float:
        start = time.monotonic()
        for _ in range(3):
            await pacer.wait(1)
        return time.monotonic() - start

    # First is free, the next two wait out the interval.
    assert asyncio.run(three()) >= 1.9


def test_pacer_waits_when_the_token_window_is_full():
    pacer = _Pacer(rpm=0, tpm=1000)

    async def run() -> None:
        await pacer.wait(900)
        # 900 + 200 exceeds 1000, so this one cannot go now.
        await asyncio.wait_for(pacer.wait(200), timeout=0.2)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(run())
