from kanalchi.text.tg_html import entities_to_html, extract_urls, html_to_text


def ent(kind: str, offset: int, length: int, **extra):
    return {"_": kind, "offset": offset, "length": length, **extra}


def test_plain_text_is_escaped():
    assert entities_to_html("a < b & c", []) == "a &lt; b &amp; c"


def test_bold_and_italic():
    html = entities_to_html("bold italic", [ent("MessageEntityBold", 0, 4), ent("MessageEntityItalic", 5, 6)])
    assert html == "<strong>bold</strong> <em>italic</em>"


def test_overlapping_entities_nest_correctly():
    # "abcd" with bold over 0-3 and italic over 2-4 → segments abc/cd must stay balanced
    html = entities_to_html("abcd", [ent("MessageEntityBold", 0, 3), ent("MessageEntityItalic", 2, 2)])
    assert html == "<strong>ab</strong><strong><em>c</em></strong><em>d</em>"
    assert html.count("<strong>") == html.count("</strong>")
    assert html.count("<em>") == html.count("</em>")


def test_text_url_and_javascript_is_neutralised():
    html = entities_to_html("click", [ent("MessageEntityTextUrl", 0, 5, url="javascript:alert(1)")])
    assert 'href="#"' in html and "javascript" not in html


def test_bare_domain_gets_https():
    html = entities_to_html("example.uz", [ent("MessageEntityUrl", 0, 10)])
    assert 'href="https://example.uz"' in html


def test_emoji_offsets_are_utf16():
    # "👍 bold" — the emoji is 2 UTF-16 units, so bold starts at offset 3
    text = "👍 bold"
    html = entities_to_html(text, [ent("MessageEntityBold", 3, 4)])
    assert html == "👍 <strong>bold</strong>"


def test_cyrillic_offsets():
    text = "Салом дунё"
    html = entities_to_html(text, [ent("MessageEntityBold", 6, 4)])
    assert html == "Салом <strong>дунё</strong>"


def test_pre_with_language():
    html = entities_to_html("x = 1", [ent("MessageEntityPre", 0, 5, language="python")])
    assert html.startswith('<pre data-lang="python">')


def test_extract_urls_dedupes_and_normalises():
    text = "site.uz and here"
    ents = [ent("MessageEntityUrl", 0, 7), ent("MessageEntityTextUrl", 12, 4, url="https://site.uz")]
    assert extract_urls(text, ents) == ["https://site.uz"]


def test_html_to_text():
    assert html_to_text("<strong>a</strong> &amp; b") == "a & b"
