"""AI kartochkalar uchun "aql": AI'ga murojaat qilmasdan bajariladigan tahlil va tekshiruvlar.

- understand(): ta'minotchi qatoridan brend va model kodini ajratish, ortiqcha so'zlarni ("NEW MODEL 2026
  VIETNAM") tashlab toza qidiruv so'rovlari tuzish; model kodining mintaqaviy variantlari (UXUZ → UXRU).
- enrich(): xususiyatlar ro'yxatidan og'irlik va o'lchamni ajratib, alohida maydonlarga yozish; yirik texnika.
- quality(): kartochka sifati (0–100) va kamchiliklar ro'yxati — xodim nimani tekshirishi kerakligini ko'radi,
  generate() esa shunga qarab ikkinchi (to'ldiruvchi) AI so'rovini yuboradi.
"""

import re
from dataclasses import dataclass, field

_CYR = re.compile(r"[а-яА-ЯёЁўқғҳЎҚҒҲ]")
# Model kodi: lotin harf va raqam aralash, kamida 4 belgi (QE75Q7FAAUXUZ, PRM-G60-E31B, 65P635, HW-Q600C/RU).
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-/.]{2,}[A-Za-z0-9]")
# Model kodi emas: o'lcham va birliklar (128GB, 60x60, 4K, 120Hz, 2000W, 55inch).
_UNIT = re.compile(
    r"^\d+([.,]\d+)?(gb|tb|mb|hz|khz|w|kw|v|kg|g|l|ml|mm|cm|m|k|mah|btu|inch|in|rpm|db|x\d+.*)$", re.I
)
_NOISE = re.compile(
    r"\b(new|model|vietnam|china|korea|turkey|uzbekistan|russia|smart|uhd|qled|oled|led|mini|full|hd|4k|8k|"
    r"wifi|wi-fi|android|tv|inverter|no\s*frost|20[12]\d)\b",
    re.I,
)
# Model kodi yo'q nomdan tashlanadigan aniq ortiqcha so'zlar (texnik belgilar — HD, LED... — qoladi).
_DROP = re.compile(r"\b(new\s+model|new|model|vietnam|china|korea|turkey|uzbekistan|russia|20[12]\d)\b", re.I)
# Bir xil modelning mintaqaviy kodlari: oxiridagi bozor qo'shimchasi farq qiladi, texnik jihati bir xil.
_REGION_SUFFIXES = ("UXUZ", "UXRU", "UXCE", "UXKZ", "UXUA", "XUZ", "XRU", "/UZ", "/RU", "/WT", "/KZ", "/EU")


@dataclass
class Understood:
    brand: str = ""
    model_code: str = ""
    queries: list[str] = field(default_factory=list)  # asosiy qidiruv so'rovlari
    fallback_queries: list[str] = field(default_factory=list)  # topilmasa — mintaqaviy variantlar bilan


def model_code_in(text: str) -> str:
    """Matndagi eng ehtimolli model kodi (bo'lmasa — bo'sh)."""
    best = ""
    for tok in _TOKEN.findall(text or ""):
        tok = tok.strip("-/.")
        if len(tok) < 4 or _UNIT.match(tok) or tok.isdigit():
            continue
        if not (re.search(r"[A-Za-z]", tok) and re.search(r"\d", tok)):
            continue
        if len(tok) > len(best):
            best = tok
    return best


def code_variants(code: str) -> list[str]:
    """Model kodining mintaqaviy variantlari: QE75Q7FAAUXUZ → QE75Q7FAAU, QE75Q7FAAUXRU."""
    up = code.upper()
    out = []
    for suffix in _REGION_SUFFIXES:
        if up.endswith(suffix) and len(up) - len(suffix) >= 5:
            base = code[: len(code) - len(suffix)]
            keep = suffix[0] if suffix[0] == "U" and len(suffix) == 4 else ""  # UXUZ → ...U + XRU
            out.append(base + keep)
            if suffix in ("UXUZ", "XUZ"):
                out.append(base + suffix.replace("UZ", "RU"))
            break
    return [v for v in dict.fromkeys(out) if v and v.upper() != up]


def understand(text: str, brand_hint: str = "", known_brands: list[str] | None = None) -> Understood:
    """Ta'minotchi qatori → brend, model kodi va qidiruv so'rovlari."""
    text = " ".join((text or "").split())
    code = model_code_in(text)
    brand = (brand_hint or "").strip()
    if not brand:
        low = text.lower()
        for b in sorted(known_brands or [], key=len, reverse=True):
            if re.search(rf"(?<![a-z0-9]){re.escape(b.lower())}(?![a-z0-9])", low):
                brand = b
                break
    if not brand and code:
        # Model kodidan oldingi lotincha so'z(lar) — odatda brend ("Телевизор TCL TV TCL 65P635").
        before = text[: text.find(code)]
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z&]+", before) if not _NOISE.fullmatch(w)]
        if words:
            brand = words[-1]
    u = Understood(brand=brand, model_code=code)
    if code:
        head = f"{brand} {code}".strip()
        u.queries = [head, f"{head} характеристики"]
        for v in code_variants(code):
            alt = f"{brand} {v}".strip()
            u.fallback_queries += [alt, f"{alt} характеристики"]
    else:
        clean = " ".join(_DROP.sub(" ", text).split()) or text
        u.queries = [clean, f"{clean} характеристики"]
    return u


# --- xususiyatlardan og'irlik va o'lcham ---
_NUM = r"(\d+(?:[.,]\d+)?)"
_WEIGHT_NAME = re.compile(r"og'?irlig|вес|масса|weight", re.I)
_PACK = re.compile(r"qadoq|упаков|короб|package|box|brutto|брутто", re.I)
_DIM_NAME = re.compile(r"o'?lcham|gabarit|габарит|размер|dimension", re.I)
_DIMS = re.compile(rf"{_NUM}\s*[x×хX*]\s*{_NUM}\s*[x×хX*]\s*{_NUM}\s*(mm|мм|cm|sm|см|m|м)?", re.I)


def _f(s: str) -> float:
    return float(s.replace(",", "."))


def enrich(result: dict) -> list[str]:
    """Bo'sh og'irlik/o'lchamni xususiyatlardan to'ldirish. Qaytaradi: nima to'ldirilgani (eslatma uchun)."""
    done = []
    specs = [s for s in result.get("specs") or [] if isinstance(s, dict)]
    if not result.get("weight_kg"):
        cands = [
            s for s in specs if _WEIGHT_NAME.search(s["name"].get("uz", "") + " " + s["name"].get("ru", ""))
        ]
        cands.sort(
            key=lambda s: bool(_PACK.search(s["name"].get("uz", "") + s["name"].get("ru", "")))
        )  # qadoqsiz avval
        for s in cands:
            m = re.search(
                rf"{_NUM}\s*(kg|кг|g|г|gr|гр)\b",
                s["value"].get("uz", "") + " " + s["value"].get("ru", ""),
                re.I,
            )
            if m:
                kg = _f(m.group(1)) / (1000 if m.group(2).lower() in ("g", "г", "gr", "гр") else 1)
                if 0.01 <= kg <= 2000:
                    result["weight_kg"] = round(kg, 2)
                    done.append("og'irlik")
                    break
    dims = result.get("dimensions_cm") or {}
    if not any(dims.get(k) for k in ("length", "width", "height")):
        cands = [
            s for s in specs if _DIM_NAME.search(s["name"].get("uz", "") + " " + s["name"].get("ru", ""))
        ]
        cands.sort(key=lambda s: bool(_PACK.search(s["name"].get("uz", "") + s["name"].get("ru", ""))))
        for s in cands:
            value = s["value"].get("uz", "") + " " + s["value"].get("ru", "")
            m = _DIMS.search(value)
            if not m:
                continue
            unit = (m.group(4) or "").lower()
            nums = [_f(m.group(i)) for i in (1, 2, 3)]
            if unit in ("mm", "мм") or (not unit and max(nums) > 400):
                nums = [n / 10 for n in nums]
            elif unit in ("m", "м"):
                nums = [n * 100 for n in nums]
            nums = sorted((max(1, round(n)) for n in nums), reverse=True)
            if nums[0] <= 500:
                # Eng katta o'lcham — balandlik yoki uzunlik: yetkazish uchun tartib muhim emas, hajm muhim.
                result["dimensions_cm"] = {"length": nums[1], "width": nums[2], "height": nums[0]}
                done.append("o'lcham")
                break
    if not result.get("is_bulky"):
        d = result.get("dimensions_cm") or {}
        if (result.get("weight_kg") or 0) >= 25 or max(
            [d.get(k) or 0 for k in ("length", "width", "height")]
        ) >= 100:
            result["is_bulky"] = True
            done.append("yirik texnika")
    return done


# --- sifat bahosi ---
ISSUES = {
    "no_category": ("Kategoriya tanlanmagan", 25),
    "new_category": ("Yangi kategoriya taklifi — tasdiqlang", 5),
    "no_images": ("Rasm yo'q", 25),
    "few_images": ("Rasm kam (3 tadan kam)", 8),
    "no_name_ru": ("Ruscha nom yo'q", 5),
    "short_description": ("Tavsif qisqa", 10),
    "no_description_ru": ("Ruscha tavsif yo'q", 5),
    "few_specs": ("Xususiyatlar kam", 12),
    "cyrillic_in_uz": ("O'zbekcha matnda ruscha so'zlar bor", 10),
    "no_weight": ("Og'irlik yo'q (yetkazish narxi uchun kerak)", 8),
    "no_dimensions": ("O'lcham yo'q (yetkazish uchun kerak)", 7),
    "no_model_code": ("Model kodi yo'q", 5),
    "low_confidence": ("AI ishonchi past — ma'lumotni tekshiring", 15),
    "duplicate": ("Katalogda shu modelli tovar bor", 20),
}
# Ikkinchi (to'ldiruvchi) AI so'rovi shu kamchiliklar uchun yuboriladi.
REFINABLE = {
    "few_specs",
    "cyrillic_in_uz",
    "no_weight",
    "no_dimensions",
    "short_description",
    "no_description_ru",
}


def cyrillic_uz_fields(result: dict) -> list[str]:
    """O'zbekcha (lotin) bo'lishi kerak, lekin kirill harfi bor matnlar."""
    out = []
    name = (result.get("name") or {}).get("uz", "")
    if _CYR.search(name):
        out.append(name)
    for s in result.get("specs") or []:
        for part in ("group", "name", "value"):
            v = (s.get(part) or {}).get("uz", "")
            if v and _CYR.search(v) and v not in out:
                out.append(v)
    return out


def quality(result: dict, *, duplicate: bool = False) -> dict:
    """{"score": 0..100, "issues": [{"code", "label"}]} — kartochka nashrga qanchalik tayyor."""
    r = result or {}
    found: list[str] = []
    if not r.get("category_slug"):
        found.append("new_category" if r.get("new_category") else "no_category")
    n_images = len(r.get("images") or [])
    if n_images == 0:
        found.append("no_images")
    elif n_images < 3:
        found.append("few_images")
    name, desc = r.get("name") or {}, r.get("description") or {}
    if not name.get("ru"):
        found.append("no_name_ru")
    if len(desc.get("uz", "")) < 400:
        found.append("short_description")
    if not desc.get("ru"):
        found.append("no_description_ru")
    if len(r.get("specs") or []) < 10:
        found.append("few_specs")
    if cyrillic_uz_fields(r) or _CYR.search(desc.get("uz", "")):
        found.append("cyrillic_in_uz")
    if not r.get("weight_kg"):
        found.append("no_weight")
    if not any((r.get("dimensions_cm") or {}).get(k) for k in ("length", "width", "height")):
        found.append("no_dimensions")
    if not r.get("model_code"):
        found.append("no_model_code")
    if r.get("confidence") is not None and r["confidence"] < 0.6:
        found.append("low_confidence")
    if duplicate:
        found.append("duplicate")
    score = max(0, 100 - sum(ISSUES[c][1] for c in found))
    return {"score": score, "issues": [{"code": c, "label": ISSUES[c][0]} for c in found]}
