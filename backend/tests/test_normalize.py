from kanalchi.text.normalize import detect_script, normalize, translit
from kanalchi.text.slug import slugify


def test_cyrillic_and_latin_uzbek_collide():
    assert normalize("Тошкент") == normalize("Toshkent") == "toshkent"
    assert normalize("O'zbekiston") == normalize("Ўзбекистон") == "ozbekiston"
    assert normalize("G‘afur G‘ulom") == "gafur gulom"


def test_russian_transliterates():
    assert normalize("Ташкент") == "tashkent"
    assert normalize("Министерство юстиции") == "ministerstvo yustitsii"


def test_diacritics_and_punctuation():
    assert normalize("  Café — №5!  ") == "cafe no5"
    assert normalize(None) == ""


def test_translit_keeps_latin():
    assert translit("Hello World") == "hello world"


def test_detect_script():
    assert detect_script("Salom") == "latn"
    assert detect_script("Салом") == "cyrl"
    assert detect_script("") == "none"


def test_slugify():
    assert slugify("Тошкент шаҳар ҳокимлиги") == "toshkent-shahar-hokimligi"
    assert slugify("!!!") == "tag"
