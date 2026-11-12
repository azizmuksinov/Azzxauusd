"""Rasm aynan shu tovarnikimi — dalillar bo'yicha baho (AI'siz, bepul).

Har bir nomzod rasm qayerdan olingani bilan keladi (qaysi sahifa, sahifa sarlavhasi, rasm tavsifi — alt).
Baho:
  3 — kuchli dalil: rasm havolasi yoki tavsifida model kodi bor; xodim bergan havolaning asosiy rasmi;
  2 — yaxshi: aynan shu model haqidagi sahifaning asosiy rasmi (schema.org / og:image), model kodi bo'yicha
      rasm qidiruvi, tavsifi tovar nomiga mos rasm;
  1 — tasdiqlanmagan: sahifa shu tovar haqida, lekin rasmning o'zida dalil yo'q (galereya yoki "o'xshash
      tovarlar" bo'lishi mumkin) — faqat ko'ruvchi AI tasdiqlasa olinadi;
  0 — olinmaydi: boshqa model (masalan QE55Q70 — biznikisi QE55Q60), boshqa tovar sahifasi, banner/logotip.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

from . import smart
from .images import is_generic, is_junk

_WORD = re.compile(r"[0-9a-zа-яёўқғҳ']+", re.I)
_STOP = {
    "uchun", "bilan", "yangi", "rangli", "для", "или", "под", "the", "and", "with", "for", "new", "купить",
    "цена", "sotib", "olish", "narxi", "online", "internet", "magazin", "магазин", "интернет", "tashkent",
    "toshkent", "ташкент", "uzbekistan", "узбекистан", "dostavka", "доставка",
}  # fmt: skip


def key(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def _code_tokens(text: str) -> set[str]:
    """Matndagi model kodiga o'xshash bo'laklar (harf+raqam, ≥4 belgi; o'lcham/birlik emas)."""
    # Faqat ajratuvchilar bo'yicha bo'linadi: "rb38-front.png" → rb38, front, png (qo'shib yuborilsa
    # "rb38front" boshqa model kodi bo'lib ko'rinardi).
    out = set()
    for p in re.split(r"[^0-9A-Za-z]+", unquote(text or "")):
        p = p.lower()
        if len(p) < 4 or p.isdigit() or p.isalpha() or smart._UNIT.match(p) or not p.isascii():
            continue
        out.add(p)
    return out


@dataclass
class Cand:
    url: str
    # have — kartochkada bor; own / ownpage — xodim bergan havolaning asosiy / sahifa ichidagi rasmi;
    # main / page — topilgan sahifaning asosiy (schema.org, og:image) / ichidagi rasmi;
    # search — rasm qidiruvi; ai_search — AI o'zi internetdan topgan; ai — AI yozgan (tekshirilmagan) havola.
    origin: str = "page"
    page: str = ""  # rasm olingan sahifa manzili
    title: str = ""  # sahifa sarlavhasi (+ schema.org nomi/SKU) yoki rasm qidiruvidagi sarlavha
    alt: str = ""  # rasm tavsifi


@dataclass
class Target:
    brand: str = ""
    code: str = ""
    name: str = ""  # nom(lar) va fayldagi qator — so'zlar bo'yicha solishtirish uchun
    codes: list[str] = field(default_factory=list)
    words: set[str] = field(default_factory=set)
    strong: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.brand_key = key(self.brand)
        codes = [key(self.code), *(key(v) for v in smart.code_variants(self.code))] if self.code else []
        self.codes = [c for c in dict.fromkeys(codes) if len(c) >= 2]
        words = {w.lower() for w in _WORD.findall(self.name or "")}
        words = {w for w in words if len(w) >= 3 and w not in _STOP and w != self.brand.lower()}
        self.words = words
        # "Kuchli" so'zlar: lotin harfli yoki raqamli (til almashganda ham o'zgarmaydi: artel, hd455, 2000w).
        self.strong = {w for w in words if w.isascii() and not w.isalpha()} | {
            w for w in words if w.isascii() and len(w) >= 4
        }

    # --- model kodi bo'yicha ---
    def has_code(self, text: str) -> bool:
        hay = key(unquote(text or ""))
        for c in self.codes:
            if c in hay and (len(c) >= 5 or (self.brand_key and self.brand_key in hay)):
                return True
        return False

    def series(self, text: str) -> bool:
        """Matnda kodimizning boshlanishi bor ("RB38" — biznikisi RB38T676FSA): shu seriya.

        Shuningdek kod oxiridagi rang/bozor harfisiz yozilgani ("PRM-G60-E31" — biznikisi PRM-G60-E31B):
        ishlab chiqaruvchi sahifasi ko'pincha shunday. Oxirida boshqa harf tursa (…E31W) — boshqa rang.
        """
        main = self.codes[0] if self.codes else ""
        if len(main) < 6:
            return False
        if any(len(t) >= 4 and main.startswith(t) for t in _code_tokens(text)):
            return True
        stem = main.rstrip("abcdefghijklmnopqrstuvwxyz")
        if stem == main or len(main) - len(stem) > 2 or len(stem) < 6:
            return False
        pattern = r"(?<![0-9a-z])" + r"[\s\-_/.]*".join(re.escape(ch) for ch in stem) + r"(?![0-9a-z])"
        return bool(re.search(pattern, unquote(text or "").lower()))

    def sibling(self, text: str) -> bool:
        """Matnda qo'shni model bor (boshi bir xil, davomi boshqa: QE55Q70 ↔ QE55Q60) — boshqa tovar."""
        main = self.codes[0] if self.codes else ""
        if len(main) < 6 or self.has_code(text):
            return False
        for t in _code_tokens(text):
            if len(t) < 5 or any(c.startswith(t) or t.startswith(c) for c in self.codes):
                continue
            common = 0
            for a, b in zip(t, main, strict=False):
                if a != b:
                    break
                common += 1
            if common >= 4:
                return True
        return False

    def foreign(self, text: str) -> bool:
        """Rasm tavsifida boshqa tovarning model kodi bor (biznikisi yo'q): "o'xshash tovarlar" rasmi."""
        if not self.codes or len(self.codes[0]) < 5 or self.has_code(text):
            return False
        for t in _code_tokens(text):
            if len(t) < 6 or sum(ch.isdigit() for ch in t) < 2 or sum(ch.isalpha() for ch in t) < 2:
                continue
            if not any(c.startswith(t) or t.startswith(c) for c in self.codes):
                return True
        return False

    # --- so'zlar bo'yicha (model kodi yo'q tovarlar va rasm tavsiflari uchun) ---
    def overlap(self, text: str) -> float:
        pool = self.strong or self.words
        if not pool:
            return 0.0
        have = {w.lower() for w in _WORD.findall(text or "")} | _code_tokens(text)
        return len(pool & have) / len(pool)

    def mentions(self, text: str) -> bool:
        """Matnda tovarga oid biror so'z (brend, nomdagi so'z) bormi."""
        low = (text or "").lower()
        return bool(self.brand and self.brand.lower() in low) or any(w in low for w in self.words)


def page_level(t: Target, title: str, url: str) -> int:
    """Sahifa shu tovar haqidami: 2 — aniq (model kodi bor), 1 — shu seriya / nomi mos, 0 — yo'q."""
    text = f"{title} {urlparse(url).path}"
    if t.codes and len(t.codes[0]) >= 4:
        if t.has_code(text):
            return 2
        if t.sibling(text):
            return 0
        return 1 if t.series(text) else 0
    score = t.overlap(text)
    brand_ok = not t.brand or t.brand.lower() in text.lower()
    if score >= 0.6 and brand_ok:
        return 2
    return 1 if score >= 0.4 and brand_ok else 0


def rate(t: Target, c: Cand) -> int:
    if c.origin == "have":
        return 3  # kartochkada allaqachon bor (xodim qoldirgan) — tegilmaydi
    if is_junk(c.url):
        return 0
    path = urlparse(c.url).path
    own_text = f"{path} {c.alt}"
    if t.has_code(own_text):
        return 3
    if t.sibling(own_text) or t.foreign(c.alt):
        return 0
    if is_generic(c.url):
        return 1 if c.origin in ("own", "main") else 0  # bo'lim/mavzu rasmi: faqat ko'ruvchi AI tasdiqlasa
    if c.origin == "own":
        return 3
    if c.origin in ("search", "ai_search"):
        # Rasm qidiruvi natijasi sarlavhasida model kodi bo'yicha saralangan; AI o'zi internetdan topgan.
        return 0 if t.sibling(c.title) else 2
    if c.origin == "ai":
        return 2 if t.series(path) else 1  # AI havolani o'ylab topgan bo'lishi mumkin
    level = 2 if c.origin == "ownpage" else page_level(t, c.title, c.page)
    if level == 0:
        return 0
    if c.origin == "main":
        return 2
    # Sahifa ichidagi rasm: tavsifiga qaraladi.
    alt = c.alt.strip()
    if alt:
        if t.series(alt) or t.overlap(alt) >= 0.5:
            return 2
        if len(alt.split()) >= 3 and not t.mentions(alt):
            return 0  # tavsifi boshqa narsa haqida ("Aksiya", "To'lov usullari", boshqa tovar nomi)
    return 2 if t.series(path) else 1


def rank(t: Target, cands: list[Cand]) -> list[tuple[int, Cand]]:
    """Har bir havola uchun eng yuqori baho; 0 baholilar tashlanadi; kuchlisi oldin (tartib saqlanadi)."""
    best: dict[str, tuple[int, Cand]] = {}
    for c in cands:
        if not isinstance(c.url, str) or urlparse(c.url).scheme not in ("http", "https"):
            continue
        r = rate(t, c)
        if c.url not in best or r > best[c.url][0]:
            best[c.url] = (r, c)
    return sorted((x for x in best.values() if x[0] > 0), key=lambda x: -x[0])
