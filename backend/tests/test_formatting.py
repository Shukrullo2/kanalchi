"""Draft sanitising and Telegram's length rules. Drafts come from a browser, so this is a trust boundary."""

import pytest

from kanalchi.telegram.formatting import (
    DraftValidationError,
    length,
    markdown_to_telegram_html,
    sanitize,
    validate,
    visible_text,
)


def test_allowed_markup_survives():
    html = "<b>bold</b> <i>italic</i> <s>gone</s> <code>x=1</code>"
    assert sanitize(html) == html


def test_disallowed_tags_are_dropped_but_their_text_is_kept():
    assert sanitize("<div>hello <script>alert(1)</script>world</div>") == "hello alert(1)world"


def test_script_href_is_refused_and_the_text_remains():
    out = sanitize('<a href="javascript:alert(1)">click</a>')
    assert "javascript" not in out
    assert "click" in out


def test_safe_href_is_kept_and_escaped():
    out = sanitize('<a href="https://gazeta.uz/?a=1&b=2">link</a>')
    assert 'href="https://gazeta.uz/?a=1&amp;b=2"' in out


def test_unbalanced_markup_is_closed():
    out = sanitize("<b>bold <i>both")
    assert out.count("<b>") == out.count("</b>") == 1
    assert out.count("<i>") == out.count("</i>") == 1


def test_br_becomes_a_newline():
    assert sanitize("a<br>b") == "a\nb"


def test_bare_text_is_escaped():
    assert sanitize("5 < 6 & 7 > 2") == "5 &lt; 6 &amp; 7 &gt; 2"


def test_spoiler_is_supported():
    assert sanitize('<span class="tg-spoiler">secret</span>') == '<span class="tg-spoiler">secret</span>'


# --------------------------------------------------------------------- lengths
def test_visible_text_ignores_markup():
    assert visible_text("<b>Salom</b> <a href='#'>dunyo</a>") == "Salom dunyo"


def test_length_counts_utf16_like_telegram():
    assert length("abc") == 3
    assert length("Салом") == 5  # Cyrillic is one unit per letter
    assert length("👍") == 2  # a surrogate pair costs two


def test_length_ignores_tags():
    assert length("<b>abc</b>") == 3


# --------------------------------------------------------------------- validation
def test_text_post_within_the_limit_passes():
    assert validate("<b>Salom</b>", has_media=False) == "<b>Salom</b>"


def test_text_post_over_4096_is_refused():
    with pytest.raises(DraftValidationError, match="4096"):
        validate("x" * 4097, has_media=False)


def test_caption_limit_is_lower_than_the_text_limit():
    long_text = "x" * 2000
    validate(long_text, has_media=False)  # fine as a text post
    with pytest.raises(DraftValidationError, match="1024"):
        validate(long_text, has_media=True)


def test_empty_post_without_media_is_refused():
    with pytest.raises(DraftValidationError, match="text or media"):
        validate("   ", has_media=False)


def test_empty_caption_with_media_is_allowed():
    assert validate("", has_media=True, media_count=1) == ""


def test_album_over_ten_items_is_refused():
    with pytest.raises(DraftValidationError, match="10"):
        validate("caption", has_media=True, media_count=11)


# --------------------------------------------------------------------- markdown
def test_markdown_bold_italic_and_links():
    out = markdown_to_telegram_html("**bold** and _italic_ and [link](https://a.uz)")
    assert "<b>bold</b>" in out
    assert "<i>italic</i>" in out
    assert '<a href="https://a.uz">link</a>' in out


def test_markdown_code_fences_become_pre():
    out = markdown_to_telegram_html("```python\nx = 1\n```")
    assert out == "<pre>x = 1</pre>"


def test_markdown_headings_become_bold_since_telegram_has_none():
    assert markdown_to_telegram_html("## Yangiliklar") == "<b>Yangiliklar</b>"


def test_markdown_bullets_become_characters():
    assert markdown_to_telegram_html("- one\n- two") == "• one\n• two"


def test_markdown_escapes_html_in_the_source():
    assert "&lt;script&gt;" in markdown_to_telegram_html("<script>")


def test_markdown_output_survives_sanitising():
    out = markdown_to_telegram_html("**bold** [l](https://a.uz) `c`")
    assert sanitize(out) == out
