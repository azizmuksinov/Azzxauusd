import pytest

from apps.core.i18n import localize
from apps.core.translit import latin_to_cyrillic


@pytest.mark.parametrize(
    ("lat", "cyr"),
    [
        ("Toshkent", "Тошкент"),
        ("O'zbekiston", "Ўзбекистон"),
        ("Farg'ona", "Фарғона"),
        ("Muzlatkich", "Музлаткич"),
        ("Kir yuvish mashinasi", "Кир ювиш машинаси"),
        ("Elektronika", "Электроника"),
        ("televizor", "телевизор"),
        ("Yangiyo'l", "Янгийўл"),
        ("ma'lumot", "маълумот"),
        ('Samsung 55" QLED', 'Самсунг 55" ҚЛЕД'),
    ],
)
def test_latin_to_cyrillic(lat, cyr):
    assert latin_to_cyrillic(lat) == cyr


def test_localize_fallbacks():
    value = {"uz": "Muzlatkich", "ru": "Холодильник"}
    assert localize(value, "ru") == "Холодильник"
    assert localize(value, "uz") == "Muzlatkich"
    assert localize(value, "uz-cyrl") == "Музлаткич"
    assert localize({"ru": "Только рус"}, "uz") == "Только рус"
    assert localize(None, "uz") == ""
