"""Icons fetched off the open web, made fit to draw on a card."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from kanalchi.tagimages import LIGHT_INK, LOGO_PX, MIN_ICON_PX, normalise_icon


def _png(size: int, colour: tuple[int, int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (size, size), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def _ico(sizes: list[int]) -> bytes:
    buffer = io.BytesIO()
    biggest = max(sizes)
    Image.new("RGBA", (biggest, biggest), (20, 30, 40, 255)).save(
        buffer, format="ICO", sizes=[(s, s) for s in sizes]
    )
    return buffer.getvalue()


def test_rejects_a_tab_sized_favicon() -> None:
    """A 16px favicon upscaled to a card is a smear; better to show nothing."""
    assert normalise_icon(_png(MIN_ICON_PX - 16, (10, 10, 10, 255))) is None


def test_rejects_undecodable_bytes() -> None:
    assert normalise_icon(b"<!doctype html><html>not an image</html>") is None


def test_rejects_a_fully_transparent_icon() -> None:
    assert normalise_icon(_png(64, (255, 255, 255, 0))) is None


def test_reads_the_largest_frame_of_an_ico() -> None:
    """`.ico` holds several sizes; the card wants the big one, as a PNG."""
    out = normalise_icon(_ico([16, 32, 128]))
    assert out is not None
    image = Image.open(io.BytesIO(out[0]))
    assert image.format == "PNG"
    assert max(image.size) == 128


def test_caps_a_large_icon_without_stretching_a_small_one() -> None:
    big = normalise_icon(_png(512, (10, 10, 10, 255)))
    small = normalise_icon(_png(64, (10, 10, 10, 255)))
    assert big is not None and small is not None
    assert max(Image.open(io.BytesIO(big[0])).size) == LOGO_PX
    assert max(Image.open(io.BytesIO(small[0])).size) == 64


@pytest.mark.parametrize(
    ("colour", "light"),
    [((250, 250, 250, 255), True), ((20, 24, 30, 255), False)],
)
def test_reports_the_ink_tone(colour: tuple[int, int, int, int], light: bool) -> None:
    """White artwork drawn for a dark header must not land on a white plate."""
    out = normalise_icon(_png(64, colour))
    assert out is not None
    assert out[1] is light


def test_ignores_transparent_pixels_when_judging_tone() -> None:
    """A dark mark on a transparent field is dark, however much field there is."""
    image = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
    for x in range(4):
        for y in range(4):
            image.putpixel((x, y), (0, 0, 0, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    out = normalise_icon(buffer.getvalue())
    assert out is not None
    assert out[1] is False
    assert LIGHT_INK < 255
