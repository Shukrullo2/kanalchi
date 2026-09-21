from kanalchi.ai.indexing import is_low_content
from kanalchi.text.chunk import approx_tokens, split_post, synthetic_chunk


def test_short_post_is_one_chunk():
    assert split_post("Salom dunyo") == ["Salom dunyo"]


def test_empty_post_has_no_chunks():
    assert split_post("") == []
    assert split_post("   ") == []


def test_long_post_splits_on_paragraphs():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(8))
    chunks = split_post(text)
    assert len(chunks) > 1
    assert all(len(c) <= 1600 for c in chunks)


def test_long_post_keeps_all_content():
    text = "\n\n".join(f"Unique{i} " + "word " * 60 for i in range(6))
    joined = " ".join(split_post(text))
    for i in range(6):
        assert f"Unique{i}" in joined


def test_single_huge_paragraph_splits_on_sentences():
    text = " ".join(f"Sentence number {i} goes here." for i in range(200))
    chunks = split_post(text)
    assert len(chunks) > 1
    assert all(len(c) <= 1700 for c in chunks)


def test_synthetic_chunk_collects_latin_names():
    out = synthetic_chunk(
        {
            "title": "Yangi qonun",
            "key_claims": ["Narx oshdi"],
            "entities": [{"normalized": "Toshkent"}, {"normalized": "Adliya vazirligi"}],
            "themes": [{"name": "qonunchilik"}],
            "custom": [{"dimension": "custom_x", "values": ["Foo"]}],
        }
    )
    for expected in ("Yangi qonun", "Narx oshdi", "Toshkent", "Adliya vazirligi", "qonunchilik", "Foo"):
        assert expected in out


def test_synthetic_chunk_dedupes_and_survives_empty():
    out = synthetic_chunk({"entities": [{"normalized": "Toshkent"}, {"normalized": "Toshkent"}]})
    assert out.count("Toshkent") == 1
    assert synthetic_chunk({}) == ""


def test_low_content_detection():
    assert is_low_content("👍", "sticker")
    assert is_low_content("", "none")
    assert not is_low_content("A sentence long enough to index", "none")
    # a short caption on a photo still carries the photo, so it is worth indexing
    assert not is_low_content("Bugun", "photo")


def test_approx_tokens_is_positive():
    assert approx_tokens("") == 1
    assert approx_tokens("word " * 100) > 100
