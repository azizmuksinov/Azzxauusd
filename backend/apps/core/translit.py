"""O'zbek lotin yozuvidan kirill yozuviga transliteratsiya.

i18n maydonlarda `uz_cyrl` bo'sh bo'lsa, `uz` qiymatidan avtomatik hosil qilinadi.
Avtomatik natija 100% emas (masalan, ruscha o'zlashmalar), shuning uchun qo'lda tuzatish mumkin.
"""

import re

_APOS = "'ʻʼ‘’`"

# Ikki harfli birikmalar birinchi tekshiriladi.
_DIGRAPHS = [
    ("o'", "ў"),
    ("g'", "ғ"),
    ("sh", "ш"),
    ("ch", "ч"),
    ("yo", "ё"),
    ("yu", "ю"),
    ("ya", "я"),
]
_SINGLE = {
    "a": "а",
    "b": "б",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "ҳ",
    "i": "и",
    "j": "ж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "қ",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "x": "х",
    "y": "й",
    "z": "з",
    "c": "с",
}
_VOWELS = set("aeiouAEIOU")


def _norm_apostrophes(text: str) -> str:
    return re.sub(f"[{re.escape(_APOS)}]", "'", text)


def _apply_case(src: str, dst: str) -> str:
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[0].isupper():
        return dst[0].upper() + dst[1:]
    return dst


def latin_to_cyrillic(text: str) -> str:
    if not text:
        return text
    text = _norm_apostrophes(text)
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        prev = text[i - 1] if i > 0 else ""
        word_start = not prev.isalpha() and prev != "'"

        pair = text[i : i + 2]
        low_pair = pair.lower()
        matched = False
        for lat, cyr in _DIGRAPHS:
            # "yo'" -> "йў" (y + o'), "ё" emas.
            if low_pair == lat and not (lat == "yo" and text[i + 2 : i + 3] == "'"):
                # "s'h" kabi ajratilgan holatlar: "sh" faqat apostrofsiz bo'lsa.
                out.append(_apply_case(pair if pair.isupper() else pair[0], cyr))
                i += 2
                matched = True
                break
        if matched:
            continue

        low = ch.lower()
        if low == "e":
            # So'z boshida va unlidan keyin "e" -> "э".
            cyr = "э" if word_start or prev in _VOWELS else "е"
            out.append(_apply_case(ch, cyr))
        elif low == "'":
            # Tutuq belgisi (ayirish belgisi) -> "ъ"
            out.append("ъ" if prev.isalpha() else ch)
        elif low in _SINGLE:
            out.append(_apply_case(ch, _SINGLE[low]))
        else:
            out.append(ch)
        i += 1
    return "".join(out)


_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i", "ь": "",
    "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}  # fmt: skip


def cyrillic_to_latin(text: str) -> str:
    """O'zbek kirill yozuvidan lotinga ("Мониторлар" → "Monitorlar"). So'z boshidagi "е" — "ye"."""
    out: list[str] = []
    for i, ch in enumerate(text or ""):
        low = ch.lower()
        if low not in _CYR_TO_LAT:
            out.append(ch)
            continue
        lat = _CYR_TO_LAT[low]
        if low == "е" and (i == 0 or not text[i - 1].isalpha()):
            lat = "ye"
        out.append(lat.capitalize() if ch.isupper() and lat else lat)
    return "".join(out)
