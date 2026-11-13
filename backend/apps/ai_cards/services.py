"""AI kartochkalar: fayl → qoralamalar → Gemini → normallashtirish → xodim tasdig'i → katalog.

Gemini javobiga ishonilmaydi: kategoriya, xususiyat va qiymatlar faqat bizdagi ro'yxatdan qabul qilinadi,
qolganlari `warnings` ga yoziladi. Kartochka faqat xodim tasdiqlagach katalogga tushadi.
"""

import json
import logging
import re
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import (
    Attribute,
    AttributeValue,
    Brand,
    Category,
    PriceHistory,
    Product,
    ProductImage,
    ProductVariant,
)
from apps.core.exceptions import ApiError
from apps.core.money import money
from apps.core.net import is_public_url

from . import client, gemini
from .excel import ExcelError, detect_currency, read_book
from .models import AiCall, CardBatch, CardDraft

D = CardDraft.Status
logger = logging.getLogger(__name__)


class CardError(ApiError):
    status_code = 409
    default_code = "ai_card_error"


# --- fayl ---
def preview_file(data: bytes) -> dict:
    """Yuklashdan oldin: tovarlar soni, ustunlar, valyuta, birinchi qatorlar (hech narsa saqlanmaydi)."""
    from apps.core.settings_registry import get_setting

    try:
        # Oldindan ko'rishda qator chegarasi yo'q: katta faylda xodim varaqlarni tanlab, bo'lib yuklaydi.
        sheets = read_book(data, 10**6)
    except ExcelError as exc:
        raise ApiError("bad_file", str(exc)) from exc
    columns, rows = sheets[0].columns, [r for sh in sheets for r in sh.rows]
    currency = detect_currency([t for sh in sheets for t in sh.texts])
    prices = [r.price for r in rows if r.price is not None]
    rate = get_setting("usd_uzs_rate")
    return {
        "rows_total": len(rows),
        "columns": columns,
        # Fayldagi varaqlar (bo'limlar): har birida nechta tovar va qaysi ustunlar tanilgani.
        "sheets": [
            {
                "name": sh.name,
                "rows": len(sh.rows),
                "with_price": sum(1 for r in sh.rows if r.price is not None),
                "columns": sh.columns,
            }
            for sh in sheets
        ],
        "max_rows": settings.AI_CARDS["MAX_ROWS"],
        "currency": currency,
        "with_price": len(prices),
        "price_min": str(min(prices)) if prices else None,
        "price_max": str(max(prices)) if prices else None,
        "usd_rate": str(rate) if rate is not None else None,
        # Namuna: har varaqning birinchi qatorlari (bitta varaq bo'lsa — 6 ta).
        "sample": [
            {
                "sheet": sh.name if len(sheets) > 1 else "",
                "row": r.number,
                "name": r.name,
                "sku": r.sku,
                "price": str(r.price) if r.price is not None else None,
                "qty": r.qty,
            }
            for sh in sheets[:6]
            for r in sh.rows[: 6 if len(sheets) == 1 else 2]
        ],
    }


@transaction.atomic
def create_batch(
    *,
    file_name: str,
    data: bytes,
    user,
    currency: str | None = None,
    usd_rate=None,
    markup_percent=None,
    sheets: list[str] | None = None,
) -> CardBatch:
    try:
        sheets = read_book(data, settings.AI_CARDS["MAX_ROWS"], only=sheets)
    except ExcelError as exc:
        raise ApiError("bad_file", str(exc)) from exc
    columns, rows = sheets[0].columns, [r for sh in sheets for r in sh.rows]
    detected = detect_currency([t for sh in sheets for t in sh.texts])
    # Artikul ustuni ishlab chiqaruvchi kodimi (part number)? Belgisi: bir necha qatorda u nomda ham
    # yozilgan. Har varaq uchun alohida aniqlanadi (bir varaqda noutbuklar, boshqasida ichki kodlar).
    from . import smart

    def _in_name(r) -> bool:
        squashed = "".join(ch for ch in r.name.lower() if ch.isalnum())
        return any(
            "".join(ch for ch in p.lower() if ch.isalnum()) in squashed for p in smart.part_numbers(r.sku)
        )

    pn_sheets = set()
    for sh in sheets:
        with_parts = [r for r in sh.rows if smart.part_numbers(r.sku)]
        if len(with_parts) >= max(2, len(sh.rows) * 0.5) and sum(map(_in_name, with_parts)) >= max(
            1, len(with_parts) * 0.15
        ):
            pn_sheets.add(sh.name)
    batch = CardBatch.objects.create(
        file_name=file_name[:255],
        columns=columns,
        rows_total=len(rows),
        currency=currency if currency in ("UZS", "USD") else detected,
        usd_rate=usd_rate,
        markup_percent=markup_percent,
        created_by=user,
    )
    CardDraft.objects.bulk_create(
        [
            CardDraft(
                batch=batch,
                row_number=r.number,
                query=f"{r.brand} {r.name}".strip()
                if r.brand and r.brand.lower() not in r.name.lower()
                else r.name,
                supplier_sku=r.sku,
                purchase_price=r.price,
                qty=r.qty,
                raw={
                    **r.raw,
                    **({"_brand": r.brand} if r.brand else {}),
                    **({"_sku_pn": True} if r.sheet in pn_sheets else {}),
                },
            )
            for r in rows
        ]
    )
    return batch


# --- katalog konteksti (Gemini'ga beriladi) ---
def catalog_context() -> list[dict]:
    """Bargi (oxirgi darajadagi) faol kategoriyalar va ularning xususiyatlari."""
    cats = (
        Category.objects.filter(is_active=True, children__isnull=True)
        .prefetch_related("attributes__options")
        .order_by("sort", "id")
    )
    out = []
    for c in cats:
        attrs = []
        for a in c.attributes.all().order_by("sort", "id"):
            item = {"code": a.code, "name": a.name.get("uz", a.code), "type": a.data_type}
            if a.unit:
                item["unit"] = a.unit
            if a.data_type == Attribute.DataType.ENUM:
                item["options"] = {o.code: o.value.get("uz", o.code) for o in a.options.all()}
            attrs.append(item)
        out.append(
            {
                "slug": c.slug,
                "name": c.name.get("uz", c.slug),
                "names": [str(v).lower() for v in c.name.values() if v],
                "attributes": attrs,
            }
        )
    return out


def _roots() -> list[tuple[str, str]]:
    return [
        (c.slug, c.name.get("uz", c.slug))
        for c in Category.objects.filter(is_active=True, parent__isnull=True).order_by("sort", "id")
    ]


def _format_context(ctx: list[dict]) -> str:
    lines = [
        "Bo'limlar (new_category.parent_slug uchun): " + ", ".join(f"{s} ({n})" for s, n in _roots()),
        "",
    ]
    for c in ctx:
        lines.append(f"- {c['slug']} ({c['name']})")
        for a in c["attributes"]:
            extra = ""
            if a["type"] == "enum":
                extra = " — variantlar: " + ", ".join(f"{k}={v}" for k, v in a["options"].items())
            elif a.get("unit"):
                extra = f", {a['unit']}"
            lines.append(f"    * {a['code']}: {a['name']} [{a['type']}{extra}]")
    return "\n".join(lines)


PROMPT = """Sen O'zbekistondagi maishiy texnika va elektronika onlayn do'konining kontent menejerisan.
Ta'minotchi faylidagi tovar: "{query}"
Fayldagi qator: {raw}

{source_rule}
va do'kon uchun tovar kartochkasini tuz. Ma'lumotni o'ylab topma: bilmasang null qo'y yoki tushirib qoldir.

Faqat bitta JSON obyekt qaytar (```json ... ``` ichida), boshqa matn yozma:
{{
  "found": true,
  "confidence": 0.0-1.0,
  "brand": "Samsung",
  "model_code": "RB38T676FSA",
  "category_slug": "<quyidagi ro'yxatdan yoki null>",
  "new_category": null,
  "name_uz": "Samsung RB38 muzlatkichi",
  "name_ru": "Холодильник Samsung RB38",
  "description_uz": "3-5 xatboshi (600-1500 belgi), o'zbek lotin yozuvida",
  "description_ru": "3-5 абзацев (600-1500 знаков) на русском",
  "warranty_months": 12,
  "weight_kg": 70.5,
  "dimensions_cm": {{"length": 60, "width": 66, "height": 203}},
  "is_bulky": true,
  "attributes": {{"<kod>": "<qiymat>"}},
  "specs": [
    {{"group_uz": "Asosiy", "group_ru": "Основные", "name_uz": "Umumiy hajm", "name_ru": "Общий объём",
      "value_uz": "385 l", "value_ru": "385 л"}}
  ],
  "image_urls": ["https://.../rasm.jpg"]
}}

Qoidalar:
- Tovar ro'yxatdagi kategoriyalardan hech biriga mos kelmasa (masalan gaz plita, lekin "Gaz plitalar" yo'q):
  category_slug: null va "new_category": {{"name_uz": "Gaz plitalar", "name_ru": "Газовые плиты",
  "parent_slug": "<bo'limlardan biri>"}} — ko'plikdagi umumiy tur nomi (brend/model emas).
  Mos kelsa — new_category: null.
  Boshqa turdagi kategoriyaga (gaz plitani "Televizorlar"ga) qo'yma.
- category_slug va attributes kodlari FAQAT quyidagi ro'yxatdan. enum uchun variant kodini yoz,
  number uchun faqat son, bool uchun true/false.
- name_uz: "Brend Model turi" ko'rinishida, qisqa; tur nomi birlikda, egalik qo'shimchasi bilan
  ("Samsung UE55U8000F televizori", "Artel HD 455 muzlatkichi") — lotin yozuvida, ruscha so'zsiz.
  Noutbuk, kompyuter, telefon va planshetda nomga konfiguratsiya ham kiradi (bir seriyaning turli
  konfiguratsiyalari bir xil nomlanmasin): "HP 250 G10 i5-1334U 8/512GB noutbuki",
  "Samsung Galaxy A55 8/256GB smartfoni"; name_ru ham shunday.
- Internet ma'lumotida model kodi faqat oxiridagi bozor qo'shimchasi bilan farq qilsa (UE55U8000FUXUZ va
  UE55U8000FUXRU, HW-Q600C va HW-Q600C/RU) — bu o'sha model: ma'lumotidan foydalan (found: true),
  model_code'ga fayldagi kodni yoz.
- Fayldagi qatorda konfiguratsiya (protsessor, xotira, SSD, ekran, rang, OS) berilgan bo'lsa — kartochka
  AYNAN shu konfiguratsiya uchun: specs'ga fayldagi qiymatlarni yoz (internetda boshqa konfiguratsiya
  topilsa ham). model_code — ishlab chiqaruvchi kodi (part number) berilgan bo'lsa o'sha.
- Aynan shu part number sahifasi topilmasa, lekin shu seriya/model sahifasi bor bo'lsa (masalan Acer
  Aspire 3 A315-24P — boshqa part number bilan): found: true. Umumiy ma'lumot (korpus, portlar, klaviatura,
  o'lcham, og'irlik) — shu seriyadan; konfiguratsiya — fayldan; confidence 0.6 dan oshmasin.
  Seriyasi ham aniqlanmasa — found: false.
- weight_kg va dimensions_cm — tovarning o'zi (qadoqsiz); ma'lumotda bo'lsa albatta to'ldir.
- Barcha matnlar (tavsif, xususiyat nomi va qiymati) o'zbek va rus tillarida — inglizcha matn qoldirma.
- description: xaridor uchun to'liq tavsif — vazifasi, asosiy imkoniyatlari va texnologiyalari (nomi va
  nima foyda berishi), boshqaruv, xavfsizlik, energiya tejash, komplektatsiya, kimga mos. Faqat
  ma'lumotdagi faktlar, reklama so'zlarisiz ("eng zo'r", "ajoyib" — yo'q). Xatboshilar orasida \n\n.
- specs: topilgan BARCHA texnik xususiyatlar (odatda 15-40 ta), guruhlab: Asosiy, O'lchamlar va og'irlik,
  Quvvat va energiya, Funksiyalar, Boshqaruv, Komplektatsiya va h.k. Qiymat birligi bilan. attributes'dagi
  ma'lumotlar ham bu yerda bo'lsin. Bilmagan xususiyatni yozma.
- is_bulky: muzlatkich, kir yuvish mashinasi, katta televizor kabi yirik texnika uchun true.
- image_urls: tovarning to'g'ridan-to'g'ri rasm fayli havolalari (jpg/png/webp), 5 tagacha, oq fonlisi afzal.
- Model topilmasa: {{"found": false}}.

Kategoriyalar va xususiyatlar:
{context}
"""


URL_PROMPT = """Sen O'zbekistondagi maishiy texnika va elektronika onlayn do'konining kontent menejerisan.
Boshqa do'kondagi tovar sahifasi: {url}
Shu sahifani o'qi (o'qib bo'lmasa, internetdan shu tovarni top) va bizning do'kon uchun kartochka tuz.
Sahifadan olingan ochiq ma'lumot (bo'lishi mumkin): {hints}

Matnni so'zma-so'z ko'chirma: faktlarni (model, xususiyatlar) saqlagan holda tavsifni o'z so'zlaring bilan
o'zbek va rus tillarida qayta yoz. Narxni olma. Ma'lumotni o'ylab topma: bilmasang null qo'y.
"""


RESEARCH_RULE = """Quyida internetdan topilgan ma'lumot (qidiruv natijalari va sahifalar matni) berilgan.
Kartochkani shu ma'lumot asosida tuz; unda yo'q faktni o'ylab topma (null qo'y). Rasm havolalari — faqat shu
ma'lumotdagi rasm fayllari. Aynan shu model topilmasa — found: false.
Sarlavhasida [SHU MODEL SAHIFASI] belgisi bor sahifa — tizim tekshirgan: u aynan shu model haqida (sahifada
kod oxiridagi rang yoki bozor qo'shimchasi — BS, -S, W, /RU — yozilmagan yoki boshqacha bo'lishi mumkin).
Bunday sahifa bo'lsa albatta found: true; model_code — fayldagi to'liq kod.

--- INTERNET MA'LUMOTI ---
{research}
--- TUGADI ---
"""


def approved_examples(limit: int = 2) -> str:
    """Xodim tasdiqlagan (tahrirlangan) oxirgi kartochkalar — do'kon uslubini o'rganish uchun namuna."""
    rows = CardDraft.objects.filter(status=D.APPROVED).order_by("-reviewed_at")[:limit]
    out = []
    for d in rows:
        r = d.result or {}
        out.append(
            json.dumps(
                {
                    "name_uz": (r.get("name") or {}).get("uz"),
                    "name_ru": (r.get("name") or {}).get("ru"),
                    "description_uz": ((r.get("description") or {}).get("uz") or "")[:400],
                    "description_ru": ((r.get("description") or {}).get("ru") or "")[:400],
                    "category_slug": r.get("category_slug"),
                    "attributes": r.get("attributes"),
                },
                ensure_ascii=False,
            )
        )
    if not out:
        return ""
    return (
        "\nDo'konimiz xodimlari tasdiqlagan kartochkalar namunasi (nom, tavsif uslubi va uzunligini"
        " shunga moslab yoz, lekin faktlarni namunadan olma):\n" + "\n".join(out) + "\n"
    )


def build_prompt(draft: CardDraft, ctx: list[dict], search: bool = True, research_text: str = "") -> str:
    return _build_prompt(draft, ctx, search, research_text) + approved_examples()


def _build_prompt(draft: CardDraft, ctx: list[dict], search: bool = True, research_text: str = "") -> str:
    if draft.raw.get("url"):
        head = URL_PROMPT.format(
            url=draft.raw["url"], hints=json.dumps(draft.raw.get("hints") or {}, ensure_ascii=False)[:4000]
        )
        if not search and research_text:
            head += "\n" + RESEARCH_RULE.format(research=research_text)
        body = PROMPT.split("Faqat bitta JSON obyekt", 1)[1]
        return head + "\nFaqat bitta JSON obyekt" + body.format(context=_format_context(ctx))
    raw = "; ".join(f"{k}: {v}" for k, v in draft.raw.items() if not str(k).startswith("_"))
    code = _understand(draft).model_code
    if code:
        raw += f"\nQatordan aniqlangan ishlab chiqaruvchi kodi (model / part number): {code}"
    if search:
        source_rule = (
            "Internetdan (avval ishlab chiqaruvchining rasmiy sayti, keyin ishonchli do'konlar) "
            "aynan shu modelni top"
        )
    elif research_text:
        source_rule = (
            RESEARCH_RULE.format(research=research_text) + "Shu ma'lumotdan aynan shu modelni aniqla"
        )
    else:
        source_rule = (
            "Bilimingdan foydalanib aynan shu modelni aniqla (ishonching komil bo'lmasa found: false qaytar)"
        )
    return PROMPT.format(query=draft.query, raw=raw, context=_format_context(ctx), source_rule=source_rule)


# --- normallashtirish ---
def _num(v) -> Decimal | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return Decimal(str(v).replace(",", ".").split()[0])
    except (InvalidOperation, IndexError):
        return None


def normalize(raw: dict, ctx: list[dict]) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    by_slug = {c["slug"]: c for c in ctx}
    slug = str(raw.get("category_slug") or "")
    if slug and slug not in by_slug:
        # AI ba'zan slug o'rniga nomini yozadi ("Muzlatkichlar") — nom bo'yicha moslash.
        low = slug.lower().strip()
        slug = next((c["slug"] for c in ctx if low in c.get("names", []) or low == c["slug"]), slug)
    new_category = None
    if slug not in by_slug:
        slug, new_category = _match_new_category(raw.get("new_category"), ctx)
        if not slug and not new_category and raw.get("category_slug"):
            warnings.append(f"Kategoriya noto'g'ri ({raw.get('category_slug')}) — qo'lda tanlang.")
    attrs_out: dict = {}
    if slug:
        defs = {a["code"]: a for a in by_slug[slug]["attributes"]}
        for code, value in (raw.get("attributes") or {}).items():
            a = defs.get(code)
            if a is None or value in (None, ""):
                continue
            if a["type"] == "enum":
                opts = a["options"]
                val = str(value)
                match = (
                    val
                    if val in opts
                    else next((k for k, v in opts.items() if v.lower() == val.lower()), None)
                )
                if match is None:
                    warnings.append(f"{a['name']}: \"{val}\" ro'yxatda yo'q.")
                    continue
                attrs_out[code] = match
            elif a["type"] == "number":
                n = _num(value)
                if n is None:
                    warnings.append(f"{a['name']}: son emas ({value}).")
                    continue
                attrs_out[code] = float(n)
            elif a["type"] == "bool":
                attrs_out[code] = (
                    value if isinstance(value, bool) else str(value).lower() in ("true", "ha", "yes", "1")
                )
            else:
                attrs_out[code] = str(value)[:255]

    def text(key, limit):
        v = raw.get(key)
        return str(v).strip()[:limit] if v else ""

    dims = raw.get("dimensions_cm") if isinstance(raw.get("dimensions_cm"), dict) else {}
    images = [
        u
        for u in (raw.get("image_urls") or [])
        if isinstance(u, str) and urlparse(u).scheme in ("http", "https")
    ][: settings.AI_CARDS["MAX_IMAGES"]]
    weight = _num(raw.get("weight_kg"))
    warranty = _num(raw.get("warranty_months"))
    confidence = _num(raw.get("confidence"))
    result = {
        "found": bool(raw.get("found", True)),
        "confidence": float(confidence) if confidence is not None else None,
        "brand": text("brand", 128),
        "model_code": text("model_code", 64),
        "category_slug": slug,
        "name": {"uz": text("name_uz", 255), "ru": text("name_ru", 255)},
        "description": {"uz": text("description_uz", 3000), "ru": text("description_ru", 3000)},
        "warranty_months": int(warranty) if warranty and 0 < warranty <= 120 else None,
        "weight_kg": float(weight) if weight and weight > 0 else None,
        "dimensions_cm": {k: int(_num(dims.get(k)) or 0) for k in ("length", "width", "height")},
        "is_bulky": bool(raw.get("is_bulky", False)),
        "attributes": attrs_out,
        "specs": normalize_specs(raw.get("specs")),
        "new_category": new_category,
        "images": images,
    }
    if not result["name"]["uz"]:
        warnings.append("O'zbekcha nom yo'q.")
    if new_category:
        warnings.append(
            f"Mos kategoriya yo'q — AI yangi kategoriya taklif qildi: «{new_category['name']['uz']}» "
            "(nashr qilinganda yaratiladi)."
        )
    if result["confidence"] is not None and result["confidence"] < 0.6:
        warnings.append("Gemini ishonchi past — ma'lumotlarni diqqat bilan tekshiring.")
    return result, warnings


def _match_new_category(value, ctx: list[dict]) -> tuple[str, dict | None]:
    """AI taklif qilgan yangi kategoriya: nomi mavjud kategoriyaga to'g'ri kelsa — o'sha (slug); aks holda
    {name:{uz,ru}, parent_slug} — nashr qilinganda yaratiladi."""
    if not isinstance(value, dict):
        return "", None
    if isinstance(value.get("name"), dict):  # allaqachon normallashgan (xodim tahriri)
        value = {"name_uz": value["name"].get("uz"), "name_ru": value["name"].get("ru"), **value}
    uz, ru = (str(value.get(k) or "").strip()[:120] for k in ("name_uz", "name_ru"))
    if not uz:
        return "", None
    if re.search(r"[а-яёўқғҳ]", uz, re.I):
        # AI o'zbekcha nomni kirillda yozgan ("Мониторлар") — do'konda lotin yozuvi ishlatiladi.
        from apps.core.translit import cyrillic_to_latin

        uz = cyrillic_to_latin(uz)
    low = {uz.lower(), ru.lower()} - {""}
    for c in ctx:
        if low & set(c.get("names", [])):
            return c["slug"], None
    parent = str(value.get("parent_slug") or "")
    if parent not in {s for s, _ in _roots()}:
        parent = ""
    return "", {"name": {"uz": uz, "ru": ru or uz}, "parent_slug": parent}


def normalize_specs(items) -> list[dict]:
    """AI xususiyatlar ro'yxati → [{group:{uz,ru}, name:{uz,ru}, value:{uz,ru}}].

    Bo'sh va takror nomlilar tashlanadi.
    """
    out, seen = [], set()
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        if isinstance(it.get("name"), dict):  # allaqachon normallashgan (xodim tahriri)
            it = {
                f"{k}_{lang}": (it.get(k) or {}).get(lang)
                for k in ("group", "name", "value")
                for lang in ("uz", "ru")
            }

        def s(key, limit=120, it=it):
            v = it.get(key)
            return str(v).strip()[:limit] if v not in (None, "", []) else ""

        name_uz, value_uz = s("name_uz"), s("value_uz", 200) or s("value", 200)
        if not name_uz or not value_uz or name_uz.lower() in seen:
            continue
        seen.add(name_uz.lower())
        out.append(
            {
                "group": {
                    "uz": s("group_uz") or "Asosiy",
                    "ru": s("group_ru") or s("group_uz") or "Основные",
                },
                "name": {"uz": name_uz, "ru": s("name_ru") or name_uz},
                "value": {"uz": value_uz, "ru": s("value_ru", 200) or value_uz},
            }
        )
    return out[:80]


from .images import MIN_SIDE as MIN_IMAGE_SIDE  # noqa: E402,F401 — eski import yo'llari uchun
from .images import image_size  # noqa: E402,F401


def pick_images(
    urls: list[str], limit: int | None = None, max_checks: int = 14, extra: list[str] | None = None
) -> tuple[list[str], list[str]]:
    """Sifatli rasmlar: tekshiriladi, kattasi oldin, takrorlari (bir xil fayl) tashlanadi va
    turli manbalardan (domenlardan) navbat bilan olinadi — bitta saytning bir xil rasmlari emas.

    `urls` — tovar sahifalari va AI topgan rasmlar (oldin); `extra` — rasm qidiruvi (keyin, to'ldirish uchun).
    """
    picked, warnings = _pick([urls, extra or []], limit or settings.AI_CARDS["MAX_IMAGES"], max_checks)
    return [f.url for f in picked], warnings


def _pick(tiers: list[list[str]], limit: int, max_checks: int = 14, keep: set[str] | None = None):
    """Pog'onalar bo'yicha (ishonchlisi oldin) yuklab tekshirilgan rasmlar: ([Fetched], ogohlantirishlar).

    Har pog'ona ichida sifatlisi oldin (o'lcham, oq fon, aniqlik — image_quality); banner, bo'sh yoki deyarli
    bo'sh rasmlar olinmaydi. `keep` — xodim qoldirgan rasmlar: sifat bo'yicha rad etilmaydi.
    """
    import hashlib
    from collections import OrderedDict

    from . import image_quality
    from .images import fingerprint, is_junk, same_picture, same_tone, tone

    seen_urls: set[str] = set()
    clean: list[list[str]] = []
    for xs in tiers:
        tier = []
        for u in dict.fromkeys(xs or []):
            if (
                isinstance(u, str)
                and urlparse(u).scheme in ("http", "https")
                and not is_junk(u)
                and u not in seen_urls
            ):
                seen_urls.add(u)
                tier.append(str(u))
        clean.append(tier)
    order = [u for tier in clean for u in tier][:max_checks]
    checked, warnings = _probe_images(order)
    usable = []
    for f in checked:
        f.quality = image_quality.analyse(f.content)
        if f.quality and f.quality.problem and f.source not in (keep or ()):
            warnings.append(f"Rasm olinmadi — {f.quality.problem}: {f.source}")
            continue
        usable.append(f)

    def best_first(f):
        return (-(f.quality.score if f.quality else 0), -f.area)

    seen, prints, picked = set(), [], []
    for tier in clean:
        members = set(tier)
        by_domain: OrderedDict[str, list] = OrderedDict()
        for f in sorted((c for c in usable if c.source in members), key=best_first):
            digest = hashlib.sha256(f.content).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            # Bir xil suratning boshqa o'lchamdagi/saytdagi nusxasi — kattasi (yoki ishonchlirog'i) qoladi.
            # Boshqa rangdagi variant (bir xil rakurs) — alohida surat: rangi ham solishtiriladi.
            fp, colour = fingerprint(f.content), tone(f.content)
            if any(same_picture(fp, other) and same_tone(colour, shade) for other, shade in prints):
                continue
            prints.append((fp, colour))
            by_domain.setdefault(urlparse(f.url).netloc.removeprefix("www."), []).append(f)
        while len(picked) < limit and any(by_domain.values()):
            for group in by_domain.values():
                if group and len(picked) < limit:
                    picked.append(group.pop(0))
    return picked, warnings


def check_images(urls: list[str]) -> tuple[list[str], list[str]]:
    """Faqat ochiladigan va yetarlicha katta (≥300 px) rasm havolalari qoldiriladi (tartib saqlanadi)."""
    checked, warnings = _probe_images(urls)
    return [f.url for f in checked], warnings


PROBE_BUDGET = 30  # soniya: bitta kartochka rasmlarini yuklab tekshirishga ajratilgan vaqt


def _probe_images(urls: list[str], referer: str = ""):
    """([Fetched], ogohlantirishlar) — ochiladigan, haqiqiy rasm, ≥300 px (kattaroq varianti bo'lsa — o'sha).
    `Fetched.source` — so'ralgan (asl) havola."""
    from concurrent.futures import ThreadPoolExecutor

    from . import images

    urls = list(urls)
    if not urls:
        return [], []
    # Parallel, lekin bitta saytga navbat bilan: sekin saytlar bir-birini kutmaydi, bir vaqtda ko'p so'rov
    # yuborilgan sayt esa bot deb bloklamaydi (rasm o'rniga sahifa qaytarardi).
    by_host: dict[str, list[str]] = {}
    for u in urls:
        by_host.setdefault(urlparse(u).netloc, []).append(u)

    import time
    from concurrent.futures import wait

    deadline = time.monotonic() + PROBE_BUDGET

    def load(group: list[str]) -> list:
        out = []
        for u in group:
            if time.monotonic() > deadline:  # sekin sayt hammani kutdirmasin — qolganlari tashlab ketiladi
                out.append(images.Fetched(u, False, reason="vaqt yetmadi (sayt sekin)"))
            else:
                out.append(images.fetch_best(u, referer=referer))
        return out

    # Bitta saytga ko'pi bilan 2 ta oqim (har biri navbat bilan); umumiy kutish — PROBE_BUDGET + biroz.
    groups: list[tuple[str, list[str]]] = []
    for host, items in by_host.items():
        groups += [(host, part) for part in (items[0::2], items[1::2]) if part]
    pool = ThreadPoolExecutor(max_workers=min(8, len(groups)))
    futures = [pool.submit(load, part) for _, part in groups]
    wait(futures, timeout=PROBE_BUDGET + 20)
    pool.shutdown(wait=False, cancel_futures=True)
    by_url = {}
    for (_, part), fut in zip(groups, futures, strict=True):
        done = fut.result() if fut.done() and not fut.cancelled() and fut.exception() is None else []
        for i, u in enumerate(part):
            by_url[u] = (
                done[i] if i < len(done) else images.Fetched(u, False, reason="vaqt yetmadi (sayt sekin)")
            )
    fetched = [by_url[u] for u in urls]
    ok, warnings = [], []
    for url, f in zip(urls, fetched, strict=True):
        if not f.ok:
            warnings.append(f"Rasm olinmadi — {f.reason}: {url}")
            continue
        f.source = url
        ok.append(f)
    return ok, warnings


# --- Rasm aynan shu tovarnikimi: dalillar bo'yicha baho + ko'ruvchi AI tekshiruvi ---
def _target(result: dict, query: str = ""):
    from . import image_match

    name = result.get("name") or {}
    return image_match.Target(
        brand=result.get("brand") or "",
        code=result.get("model_code") or "",
        name=" ".join(x for x in (name.get("uz"), name.get("ru"), query) if x),
    )


def _kind(result: dict) -> str:
    """Tovar turi (kategoriya nomi) — ko'ruvchi AI "muzlatkichmi yoki boshqa narsami" deb solishtiradi."""
    name = None
    if slug := result.get("category_slug"):
        name = Category.objects.filter(slug=slug).values_list("name", flat=True).first()
    elif isinstance(result.get("new_category"), dict):
        name = result["new_category"].get("name")
    if not isinstance(name, dict):
        return ""
    return " / ".join(dict.fromkeys(x for x in (name.get("ru"), name.get("uz")) if x))


def _label(result: dict, query: str = "") -> str:
    name = result.get("name") or {}
    head = " ".join(x for x in (result.get("brand"), result.get("model_code")) if x)
    title = name.get("ru") or name.get("uz") or query
    return f"{head} — {title}".strip(" —") if head else title


def verify_images(draft: CardDraft | None, label: str, kind: str, fetched: list, colour: str = ""):
    """Ko'ruvchi AI'ga rasmlarni ko'rsatish (≤5 ta). Natija AiCall'ga yoziladi. Ishlamasa — None."""
    from . import vision

    if not fetched or not vision.enabled():
        return None
    try:
        _check_limit()
    except ApiError:
        return None
    res = vision.verify(label, kind, [vision.Shot(f.url, f.content, f.ext) for f in fetched], colour=colour)
    if res is not None:
        AiCall.objects.create(
            provider=res.provider,
            model=res.model[:64],
            tokens_in=res.tokens_in,
            tokens_out=res.tokens_out,
            draft=draft if draft is not None and draft.pk else None,
        )
    return res


def choose_images(
    target,
    cands: list,
    *,
    draft: CardDraft | None = None,
    label: str = "",
    kind: str = "",
    limit: int | None = None,
    max_checks: int = 18,
    report: dict | None = None,
) -> tuple[list[str], list[str]]:
    """Nomzodlardan aynan shu tovar rasmlarini tanlash.

    `report` berilsa — to'ldiriladi (xodimga ko'rsatish uchun): nechta nomzod bo'lgani, nechta dalil bo'yicha
    rad etilgani, AI nechtasini ko'rib rad etgani, qaysi model ko'rgani va har rasmda nima ko'ringani.

    1) Dalillar bo'yicha baho (image_match): model kodi rasm havolasida/tavsifida, sahifa shu model haqida...
       Boshqa model yoki begona sahifa rasmlari shu yerdayoq tashlanadi.
    2) Yuklab tekshirish (o'lcham, takrorlar), ishonchlisi oldin.
    3) Ko'ruvchi AI rasmlarga qaraydi: boshqa narsa (banner, aksessuar, boshqa turdagi tovar) — olinmaydi.
       Dalili yo'q ("tasdiqlanmagan") rasm faqat AI "ha" desa qoladi; AI ishlamasa — olinmaydi.
    """
    from . import image_match, vision

    limit = limit or settings.AI_CARDS["MAX_IMAGES"]
    report = report if report is not None else {}
    ranked = image_match.rank(target, cands)
    rating = {c.url: (r, c) for r, c in ranked}
    total = len({c.url for c in cands if c.origin != "have"})
    matched = sum(1 for _, c in ranked if c.origin != "have")
    report["candidates"] = report.get("candidates", 0) + total
    report["rejected"] = report.get("rejected", 0) + total - matched
    report.setdefault("ai_removed", 0)
    report.setdefault("unconfirmed", 0)
    report.setdefault("seen", {})
    report.setdefault("vision", "")
    tiers = [[c.url for r, c in ranked if r == level] for level in (3, 2, 1)]
    can_see = vision.enabled()
    if not can_see:
        # Tasdiqlay olmaymiz — dalilsiz rasmlardan faqat xodim bergan havola sahifasinikilar (boshidagilari).
        own = [u for u in tiers[2] if rating[u][1].origin == "ownpage"][:4]
        report["unconfirmed"] += len(tiers[2]) - len(own)
        tiers[2] = own
        if settings.AI_CARDS.get("VISION", True) and not report.get("vision"):
            report["vision_error"] = vision.last_error()
    have = {c.url for _, c in ranked if c.origin == "have"}
    picked, warnings = _pick(tiers, limit + (3 if can_see else 0), max_checks, keep=have)

    def clean_first(items: list, kinds: dict | None = None) -> list:
        """Asosiy rasm — toza katalog surati (oq fonda tovarning o'zi), ular ichida eng sifatlisi."""
        rank = {"main": 0, "scene": 2, "box": 3, "info": 4}

        def order_key(f):
            q = f.quality
            kind = (kinds or {}).get(id(f), "")
            group = rank.get(kind, 0 if q is not None and q.clean else 1)
            return (group, -(q.score if q else 0))

        return sorted(items, key=order_key)

    if not can_see or not picked:
        # AI ko'rmaydi — dalil kuchi bo'yicha tartib saqlanadi, faqat toza katalog surati oldinga chiqadi.
        top = picked[:limit]
        return [f.url for f in sorted(top, key=lambda f: not (f.quality and f.quality.clean))], warnings

    # Bitta so'rov (≤5 rasm): bepul tarifda ko'ruvchi modelning daqiqalik limiti kichik. Eng kuchsiz dalilli
    # rasmlar ko'rsatiladi (tasdiqlanmaganlar, keyin "sahifaning asosiy rasmi"); model kodi rasmning o'z
    # havolasida/tavsifida yozilganlari (kuchli dalil) faqat joy qolsa tekshiriladi.
    def rate_of(f) -> int:
        return rating[f.source][0]

    exempt = [f for f in picked if rating[f.source][1].origin == "have"]
    order = sorted((f for f in picked if f not in exempt), key=rate_of)
    to_check = order[: vision.MAX_IMAGES]
    vision.clear_error()
    listed = getattr(target, "colour", "")
    res = verify_images(draft, label, kind, to_check, colour=listed) if to_check else None
    verdicts = dict(zip((id(f) for f in to_check), res.verdicts, strict=False)) if res else {}
    colours = dict(zip((id(f) for f in to_check), res.colours, strict=False)) if res else {}
    notes = dict(zip((id(f) for f in to_check), res.notes, strict=False)) if res else {}
    kinds = dict(zip((id(f) for f in to_check), res.kinds, strict=False)) if res else {}
    if res:
        report["vision"] = res.model
        report.pop("vision_error", None)
    if to_check and (res is None or any(v is None for v in res.verdicts)) and vision.last_error():
        report["vision_error"] = vision.last_error()
    kept: list = []
    removed: list[str] = []
    for f in picked:
        verdict = True if f in exempt else verdicts.get(id(f))
        if verdict is False:
            removed.append(notes.get(id(f)) or "boshqa narsa")
        elif verdict or rate_of(f) >= 2:
            kept.append(f)  # AI tasdiqladi; yoki AI ko'rmadi, lekin dalil yetarli
            if verdict and f not in exempt:
                report["seen"][f.url] = notes.get(id(f)) or "ok"
        else:
            report["unconfirmed"] += 1
    # Tartib: avval toza katalog surati (oq fonda tovarning o'zi) — u asosiy rasm bo'ladi, bir nechta bo'lsa
    # eng sifatlisi (kattasi, aniqrog'i); keyin muhitdagi suratlar, quti; matnli rasmlar (infografika) —
    # oxirida, boshqa rasm yetarli bo'lsa umuman olinmaydi (ko'pincha boshqa tildagi reklama matni bilan).
    kept = clean_first(kept, kinds)
    plain = [f for f in kept if kinds.get(id(f)) != "info"]
    if len(plain) >= 2 and len(plain) < len(kept):
        report["info_dropped"] = report.get("info_dropped", 0) + len(kept) - len(plain)
        kept = plain
    # Rang: ro'yxatda "qora" yozilgan, suratda esa oq tovar — boshqa rangdagi varianti. Mos rangdagilar oldin;
    # ular yetarli (≥2) bo'lsa boshqa rangdagilar olinmaydi (xodim qoldirgan rasmlarga tegilmaydi).
    if listed:
        other = [
            f
            for f in kept
            if f not in exempt
            and kinds.get(id(f)) in ("main", "scene", "")
            and image_match.colours_clash(listed, colours.get(id(f), ""))
        ]
        same = [f for f in kept if f not in other]
        if other and len(same) >= 2:
            report["colour_dropped"] = report.get("colour_dropped", 0) + len(other)
            kept = same
        elif other:
            kept = same + other
            report["colour_other"] = report.get("colour_other", 0) + len(other)
    report["ai_removed"] += len(removed)
    report["seen"] = {u: n for u, n in report["seen"].items() if u in {f.url for f in kept[:limit]}}
    if removed:
        what = ", ".join(dict.fromkeys(removed))[:160]
        warnings.insert(
            0, f"AI rasmlarni ko'rib tekshirdi: {len(removed)} tasi shu tovar emas — olinmadi ({what})."
        )
    return [f.url for f in kept[:limit]], warnings


def _cands_from_research(res) -> list:
    from . import image_match

    return [
        image_match.Cand(
            url=c.get("url", ""),
            origin=c.get("origin", "page"),
            page=c.get("page", ""),
            title=c.get("title", ""),
            alt=c.get("alt", ""),
        )
        for c in getattr(res, "candidates", None) or []
        if isinstance(c, dict)
    ]


# --- Gemini bilan to'ldirish ---
def cost_in_uzs(draft: CardDraft) -> Decimal | None:
    """Tannarx so'mda: fayl so'mda bo'lsa — o'zi; dollarda bo'lsa — sozlamadagi kurs bo'yicha; aks holda None.

    Valyuta va kurs taxmin qilinmaydi.
    """
    from apps.core.settings_registry import get_setting

    price = draft.purchase_price
    if price is None:
        return None
    currency = draft.batch.currency
    if currency == "UZS":
        return price
    if currency == "USD" and (rate := draft.batch.usd_rate or get_setting("usd_uzs_rate")):
        return money(price * rate)
    return None


def suggested_price(draft: CardDraft) -> Decimal | None:
    """Sotuv narxi: tannarx (so'm) × (1 + foyda %), 1 000 so'mga yuqoriga yaxlitlanadi. Foiz yo'q — None."""
    cost, markup = cost_in_uzs(draft), draft.batch.markup_percent
    if cost is None or markup is None:
        return None
    value = cost * (1 + markup / 100)
    return (value / 1000).to_integral_value(rounding=ROUND_CEILING) * 1000


def publish_many(batch: CardBatch, ids: list[int], *, user, publish: bool = True) -> dict:
    """Belgilangan kartochkalarni bir yo'la nashr qilish: narx — foyda foizi bo'yicha. Har biri alohida:
    biri xato bo'lsa, qolganlari to'xtamaydi; sababi qaytariladi."""
    ok, failed = [], []
    for d in batch.drafts.filter(pk__in=ids).select_related("batch").order_by("id"):
        name = (d.result.get("name") or {}).get("uz") or d.query
        if d.status != D.READY:
            failed.append({"id": d.id, "name": name, "reason": "tekshirish kutilayotgan kartochka emas"})
            continue
        price = suggested_price(d)
        if price is None:
            reason = "narx yo'q: fayldagi narx, valyuta/kurs yoki foyda foizi kiritilmagan"
            failed.append({"id": d.id, "name": name, "reason": reason})
            continue
        try:
            product = approve(d, user=user, price=price, publish=publish)
        except ApiError as exc:
            failed.append({"id": d.id, "name": name, "reason": str(exc.detail)})
            continue
        ok.append({"id": d.id, "name": name, "product_slug": product.slug, "price": str(price)})
    return {"published": ok, "failed": failed}


def _prompt_builder(draft: CardDraft, ctx: list[dict], found: dict):
    """Qidira oladigan AI uchun — oddiy prompt; qidira olmaydiganiga — bepul tadqiqot natijasi bilan."""
    from . import research

    def build(search: bool) -> str:
        if search or not settings.AI_CARDS.get("FREE_RESEARCH"):
            return build_prompt(draft, ctx, search)
        if "research" not in found:
            if draft.raw.get("url"):
                text, page_imgs = research.read_page_full(draft.raw["url"], limit=12000)
                found["research"] = research.Research(
                    pages=[{"url": draft.raw["url"], "title": "", "snippet": "", "hints": {}, "text": text}]
                    if text
                    else [],
                    images=page_imgs,
                )
            else:
                u = found.get("understood") or _understand(draft)
                queries = u.fallback_queries if found.get("fallback") else u.queries
                found["research"] = research.collect(
                    draft.query, brand=u.brand, queries=queries, code=u.model_code
                )
        res = found["research"]
        return build_prompt(draft, ctx, False, "" if res.empty else research.as_prompt(res))

    return build


def _understand(draft: CardDraft):
    """Ta'minotchi qatoridan brend, model kodi va toza qidiruv so'rovlari (AI'siz)."""
    from . import smart

    brands = list(Brand.objects.values_list("name", flat=True))
    raw = draft.raw or {}
    return smart.understand(
        draft.query,
        brand_hint=str(raw.get("_brand") or raw.get("brand") or ""),
        known_brands=brands,
        sku=draft.supplier_sku or "",
        sku_is_part_number=bool(raw.get("_sku_pn")),
    )


def _ask(draft: CardDraft, ctx: list[dict], found: dict):
    """Bitta AI so'rovi: (javob, JSON). So'rov AiCall'ga yoziladi (yuborilmagan bo'lsa — yozilmaydi)."""
    call = AiCall(provider=client.provider() or "-", model=client.model_name()[:64], draft=draft)
    try:
        res = client.generate(
            _prompt_builder(draft, ctx, found),
            url_context=bool(draft.raw.get("url")),
            task="url" if draft.raw.get("url") else "card",
            expect_json=True,
        )
    except client.AiError as exc:
        if exc.code != "not_configured":
            call.ok = False
            call.save()
        raise
    _fill_call(call, res)
    call.save()
    return res, client.extract_json(res.text)


def _fill_call(call: AiCall, res) -> None:
    call.provider, call.model = res.provider, res.model[:64]
    call.tokens_in, call.tokens_out = getattr(res, "tokens_in", 0), getattr(res, "tokens_out", 0)


def usage() -> dict:
    """Bugungi AI so'rovlar soni va limit (Toshkent vaqti bo'yicha kun)."""
    from apps.core.settings_registry import get_setting

    used, caps = client.used_today(), client.caps()
    tokens, cost = client.tokens_today(), client.cost_today()
    budget = get_setting("ai_daily_budget_usd")
    return {
        "tokens_today": {k: {"in": v[0], "out": v[1]} for k, v in tokens.items()},
        "cost_today_usd": round(sum(cost.values()), 4),
        "daily_budget_usd": str(budget) if budget is not None else None,
        "provider": client.provider(),
        "model": client.model_name(),
        "search": client.has_search(),
        "providers": [
            {
                **p.__dict__,
                "used_today": used.get(p.name, 0),
                "daily_cap": caps.get(p.name),
                "tokens_today": sum(tokens.get(p.name, (0, 0))),
                "cost_today_usd": cost.get(p.name),
            }
            for p in client.providers()
        ],
        "routes": {t: [p.name for p in client.chain(t)] for t in client.ROUTES} if client.active() else {},
        "used_today": AiCall.objects.filter(created_at__date=timezone.localdate()).count(),
        "daily_limit": get_setting("ai_cards_daily_limit"),
        "usd_rate": str(r) if (r := get_setting("usd_uzs_rate")) is not None else None,
    }


def _check_limit() -> None:
    u = usage()
    if u["daily_limit"] is not None and u["used_today"] >= u["daily_limit"]:
        raise ApiError(
            "ai_daily_limit",
            f"Bugungi limit tugadi ({u['daily_limit']} ta so'rov). Qolgan qatorlar ertaga davom ettiriladi.",
            status_code=429,
        )


def generate(draft: CardDraft) -> CardDraft:
    """Bitta qatorni AI orqali to'ldirish. Qatorga oid xato — FAILED; xizmat xatosi — to'xtatish."""
    if draft.status in (D.APPROVED, D.REJECTED):
        raise CardError("draft_closed", "Bu kartochka allaqachon ko'rib chiqilgan.")
    from . import smart

    understood = None if draft.raw.get("url") else _understand(draft)
    if understood and understood.model_code and not draft.raw.get("_force"):
        # Katalogda shu modelli tovar bor — AI so'rovi sarflanmaydi (qayta yuklanadigan fayllar uchun).
        existing = (
            Product.objects.filter(model_code__iexact=understood.model_code)
            .exclude(status=Product.Status.ARCHIVED)
            .first()
        )
        if existing is not None:
            draft.status, draft.product, draft.result, draft.warnings = D.DUPLICATE, existing, {}, []
            draft.error = (
                f"Katalogda bor: {existing.name.get('uz', existing.slug)} (model {understood.model_code}). "
                "AI so'rovi sarflanmadi. Baribir yangi kartochka kerak bo'lsa — «Qayta yaratish»."
            )
            draft.save(update_fields=["status", "product", "result", "warnings", "error", "updated_at"])
            return draft
    _check_limit()
    ctx = catalog_context()
    found: dict = {"understood": understood} if understood else {}  # + bepul tadqiqot natijasi
    variant_note = ""
    try:
        res, raw = _ask(draft, ctx, found)
        if (
            not normalize(raw, ctx)[0]["found"]
            and understood
            and understood.fallback_queries
            and found.get("research") is not None
        ):
            # Topilmadi — model kodining mintaqaviy variantlari bilan yana bir urinish (UXUZ → UXRU).
            found2 = {"understood": understood, "fallback": True}
            res2, raw2 = _ask(draft, ctx, found2)
            if normalize(raw2, ctx)[0]["found"]:
                res, raw, found = res2, raw2, found2
                variant_note = (
                    "Ma'lumot modelning boshqa bozor varianti bo'yicha topildi (kod oxiri farq qiladi) — "
                    "tekshiring."
                )
    except client.AiError as exc:
        logger.warning("AI xatosi (kartochka %s): %s", draft.pk, exc.message)
        if exc.code in client.SERVICE_ERRORS:
            # Qator navbatda qoladi; UI to'ldirishni to'xtatadi va sababni ko'rsatadi.
            status = 429 if exc.code == "rate_limited" else 503
            raise ApiError(f"ai_{exc.code}", exc.message, status_code=status) from exc
        draft.status, draft.error = D.FAILED, exc.message
        draft.save(update_fields=["status", "error", "updated_at"])
        return draft

    result, warnings = normalize(raw, ctx)
    if variant_note:
        warnings.insert(0, variant_note)
    if understood:
        # AI kodni/brendni yozmagan bo'lsa — fayldagi qatordan aniqlangani.
        result["model_code"] = result["model_code"] or understood.model_code[:64]
        result["brand"] = result["brand"] or understood.brand[:128]
    if not res.sources and found.get("research"):
        res.sources = found["research"].sources
    result["sources"] = res.sources[:10]
    if not result["found"]:
        # Xodim nima qidirilgani va nima o'qilganini ko'rsin (sahifa bo'sh qaytganmi, boshqa model chiqqanmi).
        note = []
        pages = getattr(found.get("research"), "pages", None) or []
        if pages:
            read = ", ".join(
                f"{urlparse(p['url']).netloc.removeprefix('www.')}"
                f"{' (shu model)' if p.get('level') else ''}"
                f" — {len(p.get('text') or '') + len(str(p.get('hints') or ''))} belgi"
                for p in pages
            )
            note = [
                f"Internetdan o'qilgan sahifalar: {read}. Aynan shu model haqida yetarli ma'lumot topilmadi."
            ]
        elif found.get("research") is not None:
            note = ["Internet qidiruvi bu tovar bo'yicha hech narsa bermadi."]
        draft.status, draft.result, draft.warnings, draft.error = D.NOT_FOUND, result, note, ""
    else:
        # Rasm nomzodlari manbasi bilan: har biri "shu tovarnikimi" deb baholanadi (image_match), keyin
        # ko'ruvchi AI tekshiradi. Begona sahifa/boshqa model rasmlari kartochkaga tushmaydi.
        from . import image_match

        own_url = draft.raw.get("url") or ""
        own_hints = draft.raw.get("hints") or {}
        cands = [
            image_match.Cand(u, "ownpage" if own_hints.get("images_guess") else "own", page=own_url)
            for u in own_hints.get("images", [])
            if isinstance(u, str)
        ]
        research_ = found.get("research")
        if research_ is not None:
            if own_url:  # havoladan import: sahifaning o'zidagi rasmlar (galereya + boshqa narsalar)
                cands += [
                    image_match.Cand(str(u), "ownpage", page=own_url, alt=getattr(u, "alt", ""))
                    for u in research_.images
                ]
            else:
                cands += _cands_from_research(research_)
        # AI bergan havolalar: o'zi internetdan qidirgan bo'lsa — ishonchliroq; aks holda o'ylab topgan
        # bo'lishi mumkin (tadqiqot sahifalaridagi havolaga mos kelsa yoki ko'ruvchi AI tasdiqlasa olinadi).
        ai_origin = "ai" if research_ is not None else "ai_search"
        cands += [image_match.Cand(u, ai_origin) for u in result["images"] if isinstance(u, str)]
        if settings.AI_CARDS.get("FREE_RESEARCH") and result.get("model_code"):
            # Rasm qidiruvi (bepul): shu model kodi yozilgan katta rasmlar — sahifa rasmlarini to'ldiradi.
            from . import research

            q = " ".join(x for x in (result.get("brand"), result.get("model_code")) if x)
            cands += [
                image_match.Cand(u, "search")
                for u in research.image_search(q, result["model_code"], brand=result.get("brand") or "")[:8]
            ]
        image_report: dict = {}
        result["images"], img_warnings = choose_images(
            _target(result, draft.query),
            cands,
            draft=draft,
            label=_label(result, draft.query),
            kind=_kind(result),
            max_checks=14,
            report=image_report,
        )
        result["image_report"] = image_report
        # Rasm kam — manba sahifalari va rasm qidiruvidan yana izlash (avto-tuzatishdagi kabi). Sahifalarni
        # o'zimiz o'qigan bo'lsak (bepul tadqiqot) nomzodlar allaqachon ko'rilgan: faqat umuman rasm bo'lmasa.
        enough = 1 if (research_ is not None and not own_url) else 2
        if len(result["images"]) < enough and settings.AI_CARDS.get("FREE_RESEARCH"):
            draft.result = result
            more, more_warnings = recover_images(draft, result["images"])
            if len(more) > len(result["images"]):
                result["images"] = more
            img_warnings += more_warnings
        # "Juda kichik" eskizlar haqidagi xabarlar xodimga kerak emas — faqat rasm umuman topilmasa sababi;
        # AI ko'rigi nimani olib tashlagani esa doim ko'rsatiladi.
        seen_note = [w for w in img_warnings if w.startswith("AI rasmlarni")][:1]
        img_warnings = seen_note + ([] if result["images"] else list(dict.fromkeys(img_warnings))[:2])
        img_warnings = list(dict.fromkeys(img_warnings))
        warnings += img_warnings
        if result["model_code"] and Product.objects.filter(model_code__iexact=result["model_code"]).exists():
            warnings.insert(0, f"Katalogda {result['model_code']} modelli tovar allaqachon bor.")
        # Aql: og'irlik/o'lchamni xususiyatlardan ajratish; yetishmaganini ikkinchi so'rov bilan to'ldirish.
        smart.enrich(result)
        notes = refine(draft, result, found) if settings.AI_CARDS.get("REFINE", True) else []
        smart.enrich(result)
        if notes:
            warnings.append(f"AI qo'shimcha so'rov bilan to'ldirdi: {', '.join(notes)}.")
        draft.status, draft.result, draft.warnings, draft.error = D.READY, result, warnings, ""
    draft.model_used = f"{res.provider}: {res.model}"[:64]
    if res.fallback_notes:
        draft.warnings = [*draft.warnings, *[f"Zaxira AI ishlatildi — {n}" for n in res.fallback_notes]][:30]
    draft.save(update_fields=["status", "result", "warnings", "error", "model_used", "updated_at"])
    return draft


REFINE_PROMPT = """Tovar: {label}. Kartochka tayyor, lekin quyidagilar yetishmaydi. FAQAT shularni top va ber:
{asks}
{source}
Faqat bitta JSON obyekt qaytar (```json ... ``` ichida); bilmaganingni yozma (null qo'y yoki tushirib qoldir):
{{"weight_kg": 15.3, "dimensions_cm": {{"length": 123, "width": 6, "height": 71}},
 "specs": [{{"group_uz": "Ekran", "group_ru": "Экран", "name_uz": "Yangilanish chastotasi",
   "name_ru": "Частота обновления",
   "value_uz": "60 Hz", "value_ru": "60 Гц"}}],
 "description_uz": "...", "description_ru": "...",
 "uz_fixes": {{"<asl matn>": "<o'zbekcha, lotin yozuvida>"}}}}
Ma'lumotni o'ylab topma. O'zbekcha matnlar faqat lotin yozuvida."""


def refine(draft: CardDraft, result: dict, found: dict) -> list[str]:
    """Kartochkaning yetishmayotgan joylarini bitta qo'shimcha AI so'rovi bilan to'ldirish.

    Faqat kerak bo'lsa (og'irlik, o'lcham, xususiyatlar kam, o'zbekcha matnda kirill, tavsif qisqa).
    Xato bo'lsa —
    kartochka o'zgarmaydi. Qaytaradi: nimalar to'ldirilgani.
    """
    from . import research, smart

    issues = {i["code"] for i in smart.quality(result)["issues"]} & smart.REFINABLE
    if not issues:
        return []
    try:
        _check_limit()
    except ApiError:
        return []
    desc = result.get("description") or {}
    asks = []
    if "no_weight" in issues:
        asks.append("- weight_kg: tovarning o'z og'irligi (qadoqsiz), kg")
    if "no_dimensions" in issues:
        asks.append("- dimensions_cm: tovarning o'z o'lchami (qadoqsiz), sm")
    if "few_specs" in issues:
        have = ", ".join(s["name"]["uz"] for s in result.get("specs") or []) or "yo'q"
        asks.append(f"- specs: kartochkada yo'q texnik xususiyatlar, 10-25 ta (hozir borlari: {have})")
    cyr = smart.cyrillic_uz_fields(result)
    if cyr:
        asks.append(
            "- uz_fixes: quyidagi matnlarni o'zbek tiliga, lotin yozuvida o'gir: "
            + json.dumps(cyr[:40], ensure_ascii=False)
        )
    if "short_description" in issues or smart._CYR.search(desc.get("uz", "")):
        asks.append("- description_uz: 3-5 xatboshi (600-1500 belgi), lotin yozuvida, faktlar bilan")
    if "no_description_ru" in issues or "short_description" in issues:
        asks.append("- description_ru: 3-5 абзацев (600-1500 знаков)")
    if not asks:
        return []
    label = " ".join(x for x in (result.get("brand"), result.get("model_code")) if x) or draft.query
    label = f"{(result.get('name') or {}).get('uz') or draft.query} ({label})"
    text = ""
    base = found.get("research")
    if draft.raw.get("url"):
        if base is not None and not base.empty:
            text = research.as_prompt(base, limit=9000)
        elif settings.AI_CARDS.get("FREE_RESEARCH"):
            text = research.read_page_full(draft.raw["url"], limit=9000)[0]
    elif settings.AI_CARDS.get("FREE_RESEARCH"):
        short = " ".join(x for x in (result.get("brand"), result.get("model_code")) if x) or draft.query
        extra = research.collect(
            short,
            brand=result.get("brand") or "",
            max_pages=2,
            queries=[
                f"{short} технические характеристики вес габариты",
                f"{short} specifications dimensions weight",
            ],
        )
        if not extra.empty:
            text = research.as_prompt(extra, limit=8000)
        elif base is not None and not base.empty:
            text = research.as_prompt(base, limit=8000)

    def build(search: bool) -> str | None:
        if text:
            source = f"--- INTERNET MA'LUMOTI ---\n{text}\n--- TUGADI ---"
        elif search:
            source = "Ma'lumotni internetdan top (ishlab chiqaruvchi sayti, yirik do'konlar)."
        else:
            return None  # ma'lumot yo'q va xizmat qidira olmaydi — o'ylab topmasin
        sent.append(1)
        return REFINE_PROMPT.format(label=label, asks="\n".join(asks), source=source)

    sent: list[int] = []  # so'rov haqiqatan yuborilganmi (AiCall hisobi uchun)

    call = AiCall(provider=client.provider() or "-", model=client.model_name()[:64], draft=draft)
    try:
        res = client.generate(build, task="card", expect_json=True)
        _fill_call(call, res)
        call.save()
        data = client.extract_json(res.text)
    except client.AiError as exc:
        logger.warning("To'ldiruvchi AI so'rovi (kartochka %s): %s", draft.pk, exc.message)
        if sent and exc.code != "not_configured":
            call.ok = False
            call.save()
        return []
    if not isinstance(data, dict):
        return []

    notes = []
    weight = _num(data.get("weight_kg"))
    if not result.get("weight_kg") and weight and 0 < weight <= 2000:
        result["weight_kg"] = float(weight)
        notes.append("og'irlik")
    dims = data.get("dimensions_cm") if isinstance(data.get("dimensions_cm"), dict) else {}
    clean = {k: int(_num(dims.get(k)) or 0) for k in ("length", "width", "height")}
    have_dims = result.get("dimensions_cm") or {}
    if not all(have_dims.get(k) for k in ("length", "width", "height")) and all(
        0 < v <= 500 for v in clean.values()
    ):
        result["dimensions_cm"] = clean
        notes.append("o'lcham")
    before = len(result.get("specs") or [])
    merged = normalize_specs([*(result.get("specs") or []), *(data.get("specs") or [])])
    if len(merged) > before:
        result["specs"] = merged
        notes.append(f"xususiyatlar {before} → {len(merged)}")
    fixes = data.get("uz_fixes") if isinstance(data.get("uz_fixes"), dict) else {}
    fixes = {k: str(v).strip() for k, v in fixes.items() if v and not smart._CYR.search(str(v))}
    if fixes:
        fixed = 0
        name = result.get("name") or {}
        if name.get("uz") in fixes:
            name["uz"] = fixes[name["uz"]][:255]
            fixed += 1
        for s in result.get("specs") or []:
            for part in ("group", "name", "value"):
                if (s.get(part) or {}).get("uz") in fixes:
                    s[part]["uz"] = fixes[s[part]["uz"]][:200]
                    fixed += 1
        if fixed:
            notes.append(f"o'zbekchaga o'girildi: {fixed} ta")
    new_uz, new_ru = (
        str(data.get("description_uz") or "").strip(),
        str(data.get("description_ru") or "").strip(),
    )
    old_uz_bad = bool(smart._CYR.search(desc.get("uz", "")))
    if new_uz and not smart._CYR.search(new_uz) and (len(new_uz) > len(desc.get("uz", "")) or old_uz_bad):
        result.setdefault("description", {})["uz"] = new_uz[:3000]
        notes.append("tavsif")
    if new_ru and len(new_ru) > len(desc.get("ru", "")):
        result.setdefault("description", {})["ru"] = new_ru[:3000]
    return notes


def create_from_url(url: str, *, user) -> CardDraft:
    """Boshqa do'kondagi tovar havolasi (Uzum, Ozon, Yandex Market...) → AI kartochka (qoralama)."""
    from . import page_hints

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiError("bad_url", "To'g'ri havola kiriting (https://...).")
    if not is_public_url(url):
        raise ApiError("bad_url", "Bu manzilni ochib bo'lmaydi (ichki tarmoq).")
    hints = page_hints.fetch(url)
    with transaction.atomic():
        batch = CardBatch.objects.create(
            file_name=url[:255], columns={"url": parsed.netloc}, rows_total=1, created_by=user
        )
        draft = CardDraft.objects.create(
            batch=batch,
            row_number=1,
            query=(hints.get("name") or url)[:500],
            raw={"url": url, "hints": hints},
        )
    return generate(draft)


def requeue_failed(batch: CardBatch) -> int:
    """Xato bo'lgan qatorlarni qayta navbatga qo'yish."""
    return batch.drafts.filter(status=D.FAILED).update(status=D.PENDING, error="", updated_at=timezone.now())


def next_pending(batch: CardBatch) -> CardDraft | None:
    return batch.drafts.filter(status=D.PENDING).order_by("id").first()


# --- xodim tahriri va tasdig'i ---
def update_result(draft: CardDraft, data: dict) -> CardDraft:
    """Xodim tahrirlagan kartochka qayta tekshiriladi (kategoriya, xususiyatlar)."""
    if draft.status != D.READY:
        raise CardError("draft_not_ready", "Faqat tekshirish kutilayotgan kartochkani tahrirlash mumkin.")
    ctx = catalog_context()
    merged = {**draft.result, **data}
    if "attributes" in data:
        # Xususiyatlar birlashtiriladi; qiymati null bo'lgani o'chiriladi.
        attrs = {**draft.result.get("attributes", {}), **data["attributes"]}
        merged["attributes"] = {k: v for k, v in attrs.items() if v is not None}
    raw = {
        **merged,
        "name_uz": merged.get("name", {}).get("uz"),
        "name_ru": merged.get("name", {}).get("ru"),
        "description_uz": merged.get("description", {}).get("uz"),
        "description_ru": merged.get("description", {}).get("ru"),
        "image_urls": merged.get("images", []),
    }
    result, warnings = normalize(raw, ctx)
    result["sources"] = draft.result.get("sources", [])
    if report := draft.result.get("image_report"):
        result["image_report"] = report
    draft.result, draft.warnings = result, warnings
    draft.save(update_fields=["result", "warnings", "updated_at"])
    return draft


def _unique_slug(base: str) -> str:
    base = slugify(base)[:180] or "tovar"
    slug, n = base, 2
    while Product.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def _brand(name: str) -> Brand | None:
    if not name:
        return None
    brand = (
        Brand.objects.filter(name__iexact=name).first() or Brand.objects.filter(slug=slugify(name)).first()
    )
    return brand or Brand.objects.create(name=name, slug=slugify(name) or "brand")


def _download(url: str) -> ContentFile | None:
    from . import images

    f = images.fetch(url)
    if not f.ok:
        return None
    # Do'konda suratlar bir xil ko'rinsin: oq fondagi surat chetidagi bo'sh joy kesilib, kvadrat qilinadi;
    # juda katta surat kichraytiriladi. O'zgartirish shart bo'lmasa — asl fayl saqlanadi.
    if f.ext != "gif":
        try:
            from . import image_quality

            if ready := image_quality.normalize(f.content):
                return ContentFile(ready[0], name=f"ai.{ready[1]}")
        except Exception:  # noqa: BLE001 — tekislab bo'lmasa asl fayl saqlanadi
            logger.warning("Rasmni tekislab bo'lmadi: %s", url)
    if f.ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        # AVIF/HEIC eski brauzer va telefonlarda ochilmaydi — do'kon uchun JPEG'ga o'tkaziladi.
        try:
            import io

            from PIL import Image

            with Image.open(io.BytesIO(f.content)) as im:
                im = im.convert("RGBA")
                flat = Image.new("RGB", im.size, "white")
                flat.paste(im, mask=im.split()[-1])
                out = io.BytesIO()
                flat.save(out, "JPEG", quality=90)
            return ContentFile(out.getvalue(), name="ai.jpg")
        except Exception:  # noqa: BLE001 — o'qilmasa asl fayl saqlanadi
            logger.warning("Rasmni JPEG'ga o'tkazib bo'lmadi: %s", url)
    return ContentFile(f.content, name=f"ai.{f.ext}")


@transaction.atomic
def approve(draft: CardDraft, *, user, price, old_price=None, sku: str = "", publish: bool = True) -> Product:
    draft = CardDraft.objects.select_for_update().get(pk=draft.pk)
    if draft.status != D.READY:
        raise CardError("draft_not_ready", "Faqat tekshirish kutilayotgan kartochkani nashr qilish mumkin.")
    r = draft.result
    category = Category.objects.filter(slug=r.get("category_slug") or "", is_active=True).first()
    if category is None and r.get("new_category"):
        from apps.catalog.services import find_or_create_category

        nc = r["new_category"]
        category, _ = find_or_create_category(nc["name"], nc.get("parent_slug", ""))
    if category is None:
        raise ApiError("category_required", "Kategoriyani tanlang.")
    if not (r.get("name") or {}).get("uz"):
        raise ApiError("name_required", "O'zbekcha nomni kiriting.")
    price = money(price)
    if old_price is not None and money(old_price) <= price:
        raise ApiError("bad_old_price", "Eski narx yangi narxdan katta bo'lishi kerak.")
    sku = (sku or draft.supplier_sku or f"AI-{draft.pk}").strip()[:64]
    if ProductVariant.objects.filter(sku=sku).exists():
        raise ApiError("sku_exists", f"{sku} artikulli tovar allaqachon bor.", status_code=409)

    name = {k: v for k, v in r["name"].items() if v}
    product = Product.objects.create(
        category=category,
        brand=_brand(r.get("brand", "")),
        slug=_unique_slug(name["uz"]),
        name=name,
        description={k: v for k, v in (r.get("description") or {}).items() if v},
        model_code=r.get("model_code", ""),
        specs=r.get("specs") or [],
        status=Product.Status.ACTIVE if publish else Product.Status.DRAFT,
        warranty_months=r.get("warranty_months") or 12,
        is_bulky=bool(r.get("is_bulky")),
        serial_tracking=Product.SerialTracking.NONE,
    )
    dims = r.get("dimensions_cm") or {}
    variant = ProductVariant.objects.create(
        product=product,
        sku=sku,
        price=price,
        old_price=money(old_price) if old_price is not None else None,
        cost_price=cost_in_uzs(draft),
        weight_kg=Decimal(str(r.get("weight_kg") or 0)),
        length_cm=dims.get("length") or 0,
        width_cm=dims.get("width") or 0,
        height_cm=dims.get("height") or 0,
    )
    PriceHistory.objects.create(
        variant=variant,
        price=price,
        old_price=variant.old_price,
        source=PriceHistory.Source.MANUAL,
        changed_by=user,
    )
    attrs = {a.code: a for a in category.attributes.prefetch_related("options")}
    for code, value in (r.get("attributes") or {}).items():
        a = attrs.get(code)
        if a is None:
            continue
        av = AttributeValue(product=product, attribute=a)
        if a.data_type == Attribute.DataType.ENUM:
            av.option = next((o for o in a.options.all() if o.code == value), None)
            if av.option is None:
                continue
        elif a.data_type == Attribute.DataType.NUMBER:
            av.value_number = Decimal(str(value))
        elif a.data_type == Attribute.DataType.BOOL:
            av.value_bool = bool(value)
        else:
            av.value_text = {"uz": str(value)}
        av.save()

    failed = [url for i, url in enumerate(r.get("images") or []) if not _attach_image(product, url, i)]
    product.save()  # qidiruv matni (signal) xususiyatlar bilan yangilanadi

    draft.status = D.APPROVED
    draft.product = product
    draft.reviewed_by = user
    draft.reviewed_at = timezone.now()
    if failed:
        draft.warnings = [*draft.warnings, *[f"Rasm yuklanmadi: {u}" for u in failed]]
    draft.save(update_fields=["status", "product", "reviewed_by", "reviewed_at", "warnings", "updated_at"])
    return product


def reject(draft: CardDraft, *, user) -> CardDraft:
    if draft.status in (D.APPROVED, D.REJECTED):
        raise CardError("draft_closed", "Bu kartochka allaqachon ko'rib chiqilgan.")
    draft.status, draft.reviewed_by, draft.reviewed_at = D.REJECTED, user, timezone.now()
    draft.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    return draft


def reset(draft: CardDraft) -> CardDraft:
    """Qayta yaratish uchun navbatga qaytarish."""
    if draft.status in (D.APPROVED, D.REJECTED):
        raise CardError("draft_closed", "Bu kartochka allaqachon ko'rib chiqilgan.")
    if draft.status == D.DUPLICATE:
        # Xodim ataylab qayta yaratmoqda — takror tekshiruvi o'tkazib yuboriladi.
        draft.raw = {**draft.raw, "_force": True}
        draft.product = None
    draft.status, draft.result, draft.warnings, draft.error = D.PENDING, {}, [], ""
    draft.save(update_fields=["status", "result", "warnings", "error", "raw", "product", "updated_at"])
    return draft


# --- mavjud tovarlarga rasm topish ---
IMAGE_PROMPT = """Internetdan quyidagi tovarning rasmlarini top: "{name}"{model}.
Avval ishlab chiqaruvchining rasmiy sayti, keyin yirik do'konlar. Faqat aynan shu modelning rasmi bo'lsin.
Faqat JSON qaytar (```json ... ``` ichida): {{"image_urls": ["https://.../rasm.jpg"]}} — to'g'ridan-to'g'ri
rasm fayli havolalari (jpg/png/webp), oq fonlisi afzal, 5 tagacha. Topilmasa: {{"image_urls": []}}"""


def find_images(product: Product, *, max_images: int = 3, free_only: bool = False) -> int:
    """Rasmsiz tovarga rasm topib yuklash: avval bepul yo'l (qidiruv + sahifa rasmlari), keyin — internetdan
    qidira oladigan AI (`free_only` bo'lsa bu qadam yo'q). Qaytaradi: yuklangan rasmlar soni."""
    if product.images.exists():
        return 0
    name = " ".join(x for x in [product.brand.name if product.brand else "", product.name.get("uz", "")] if x)
    # 1) Bepul yo'l: qidiruv + sahifalarning o'z rasmlari (schema.org / og:image) — AI so'rovisiz.
    if settings.AI_CARDS.get("FREE_RESEARCH"):
        from . import research

        found = research.collect(
            f"{name} {product.model_code}".strip(), brand=product.brand.name if product.brand else ""
        )
        urls, _ = choose_images(
            _product_target(product), _cands_from_research(found), label=name, kind=_product_kind(product)
        )
        if saved := _save_images(product, urls, max_images):
            return saved
    if free_only:
        return 0
    # 2) AI orqali.
    _check_limit()
    prompt = IMAGE_PROMPT.format(
        name=name, model=f" (model: {product.model_code})" if product.model_code else ""
    )
    call = AiCall(provider=client.provider() or "-", model=client.model_name()[:64])
    try:
        res = None
        try:
            # Internetdan o'zi qidira oladigan AI uchun (qidira olmaydiganiga havola o'ylab topdirilmaydi).
            res = client.generate(lambda search: prompt if search else None, task="images")
        finally:
            if res is not None:
                _fill_call(call, res)
            call.save()
        urls = client.extract_json(res.text).get("image_urls") or []
    except client.AiError as exc:
        AiCall.objects.filter(pk=call.pk).update(ok=False)
        logger.warning("Rasm qidiruvi xatosi (%s): %s", product.slug, exc.message)
        if exc.code in client.SERVICE_ERRORS:
            raise
        return 0
    from . import image_match

    urls, _ = choose_images(
        _product_target(product),
        [image_match.Cand(u, "ai_search") for u in urls if isinstance(u, str)],
        label=name,
        kind=_product_kind(product),
    )
    return _save_images(product, urls, max_images)


def _product_target(product: Product):
    from . import image_match

    return image_match.Target(
        brand=product.brand.name if product.brand else "",
        code=product.model_code or "",
        name=" ".join(x for x in (product.name.get("uz"), product.name.get("ru")) if x),
    )


def _product_kind(product: Product) -> str:
    name = product.category.name if product.category_id else {}
    return " / ".join(dict.fromkeys(x for x in (name.get("ru"), name.get("uz")) if x))


def _save_images(product: Product, urls: list, max_images: int) -> int:
    urls = [u for u in urls if isinstance(u, str) and urlparse(u).scheme in ("http", "https")]
    ok, _ = check_images(urls[: settings.AI_CARDS["MAX_IMAGES"]])
    saved = 0
    for i, url in enumerate(ok[:max_images]):
        saved += _attach_image(product, url, i)
    return saved


def _attach_image(product: Product, url: str, sort: int) -> bool:
    """Rasmni yuklab saqlash. Disk yozilmasa — tashqi havola bilan qoladi (nashr to'xtamaydi)."""
    content = _download(url)
    if content is None:
        return False
    img = ProductImage(
        product=product, external_url=url[:500], alt={"uz": product.name.get("uz", "")}, sort=sort
    )
    try:
        img.file.save(content.name, content, save=False)
    except OSError as exc:
        logger.error("Rasm diskka yozilmadi (%s): %s — tashqi havola saqlanadi", url, exc)
        img.file = None
    img.save()
    return True


def check_providers() -> list[dict]:
    """Har bir xizmatga kichik so'rov: ishlaydimi, qancha vaqt, javob sarlavhalaridagi limitlar.

    Har ulangan xizmatga 1 ta so'rov ketadi (kunlik limitga yoziladi).
    """
    import time

    from . import gemini, openai_compat

    out = []
    for p in client.providers():
        row = {
            "name": p.name,
            "label": p.label,
            "model": p.model,
            "configured": p.configured,
            "missing": p.missing,
        }
        if p.configured:
            started = time.monotonic()
            try:
                if p.name == "gemini":
                    res = gemini.generate("Faqat OK deb javob ber.", search=False, max_tokens=16)
                else:
                    res = openai_compat.generate(
                        "Faqat OK deb javob ber.", client._config(p.name), max_tokens=16
                    )
                row.update(ok=True, reply=res.text.strip()[:40], served_model=res.model, limits=res.limits)
            except client.AiError as exc:
                row.update(ok=False, error=exc.message[:300])
            row["seconds"] = round(time.monotonic() - started, 1)
            AiCall.objects.create(provider=p.name, model=p.model[:64], ok=bool(row.get("ok")))
            if p.name == "openrouter":
                row["account"] = _openrouter_key_info(client._config(p.name))
        out.append(row)
    out.append(_check_vision())
    return out


def _check_vision() -> dict:
    """Ko'ruvchi AI ishlayaptimi: kichik sinov rasmi yuboriladi (1 so'rov)."""
    import time

    from django.core.cache import cache

    from . import vision

    row = {
        "name": "vision",
        "label": "Rasmni ko'rib tekshirish",
        "model": "",
        "configured": bool(settings.AI_CARDS.get("VISION", True))
        and bool(
            (settings.AI_PROVIDER_CONFIG.get("groq") or {}).get("api_key") or settings.GEMINI.get("API_KEY")
        ),
        "missing": "GROQ_API_KEY yoki GEMINI_API_KEY",
    }
    if not row["configured"]:
        return row
    # Tekshiruv — yangidan: eslab qolingan model va kutish belgilari tozalanadi.
    cache.delete_many(
        [vision._MODEL_KEY.format("groq"), vision._COOLDOWN.format("groq"), vision._COOLDOWN.format("gemini")]
    )
    started = time.monotonic()
    res = vision.verify("violet square (test image)", "", [vision.Shot("", vision.test_png(), "png")])
    row["seconds"] = round(time.monotonic() - started, 1)
    if res is None:
        row.update(ok=False, error="Rasm ko'ra oladigan model javob bermadi (model yo'q yoki limit tugagan).")
    else:
        row.update(
            ok=True, reply=(res.notes[0] or "javob oldi")[:40], served_model=res.model, model=res.model
        )
        AiCall.objects.create(
            provider=res.provider, model=res.model[:64], tokens_in=res.tokens_in, tokens_out=res.tokens_out
        )
    return row


def _openrouter_key_info(cfg: dict) -> dict:
    try:
        with gemini.client(timeout=15) as c:
            r = c.get(
                "https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {cfg['api_key']}"}
            )
        return (r.json() or {}).get("data", {}) if r.status_code == 200 else {"status": r.status_code}
    except (httpx.HTTPError, ValueError):
        return {}


# --- zaxira: yuklamani eksport/import (AI so'rovlari qayta sarflanmasin) ---
EXPORT_FIELDS = (
    "row_number",
    "query",
    "supplier_sku",
    "purchase_price",
    "qty",
    "raw",
    "status",
    "result",
    "warnings",
    "error",
    "model_used",
)


def export_batch(batch: CardBatch) -> dict:
    return {
        "format": "ai-cards/1",
        "file_name": batch.file_name,
        "columns": batch.columns,
        "rows_total": batch.rows_total,
        "currency": batch.currency,
        "usd_rate": str(batch.usd_rate) if batch.usd_rate is not None else None,
        "markup_percent": str(batch.markup_percent) if batch.markup_percent is not None else None,
        "drafts": [
            {
                f: (str(v) if f == "purchase_price" and v is not None else v)
                for f in EXPORT_FIELDS
                for v in [getattr(d, f)]
            }
            for d in batch.drafts.order_by("id")
        ],
    }


@transaction.atomic
def import_batch(data: dict, *, user) -> CardBatch:
    """Eksport faylidan tiklash (AI so'rovisiz).

    Nashr qilinganlar "tekshirish kutilmoqda" bo'lib qaytadi — tovar bazada bo'lmasligi mumkin.
    """
    if (
        not isinstance(data, dict)
        or data.get("format") != "ai-cards/1"
        or not isinstance(data.get("drafts"), list)
    ):
        raise ApiError("bad_backup", "Bu AI kartochkalar zaxira fayli emas.")
    statuses = set(D.values)
    batch = CardBatch.objects.create(
        file_name=str(data.get("file_name") or "import")[:255],
        columns=data.get("columns") or {},
        rows_total=int(data.get("rows_total") or len(data["drafts"])),
        currency=data.get("currency") if data.get("currency") in ("UZS", "USD") else "",
        usd_rate=Decimal(str(data["usd_rate"])) if data.get("usd_rate") else None,
        markup_percent=Decimal(str(data["markup_percent"]))
        if data.get("markup_percent") not in (None, "")
        else None,
        created_by=user,
    )
    rows = []
    for item in data["drafts"]:
        if not isinstance(item, dict) or not item.get("query"):
            continue
        status = item.get("status") if item.get("status") in statuses else D.PENDING
        if status == D.APPROVED:
            status = D.READY
        price = item.get("purchase_price")
        rows.append(
            CardDraft(
                batch=batch,
                row_number=int(item.get("row_number") or len(rows) + 1),
                query=str(item["query"])[:500],
                supplier_sku=str(item.get("supplier_sku") or "")[:64],
                purchase_price=Decimal(str(price)) if price not in (None, "") else None,
                qty=item.get("qty"),
                raw=item.get("raw") or {},
                status=status,
                result=item.get("result") or {},
                warnings=item.get("warnings") or [],
                error=str(item.get("error") or ""),
                model_used=str(item.get("model_used") or "")[:64],
            )
        )
    CardDraft.objects.bulk_create(rows)
    return batch


# --- kategoriyalarni ommaviy aniqlash (bir AI so'rovida ko'p kartochka — arzon) ---
CATEGORIZE_PROMPT = """Onlayn do'kon kategoriyalari ro'yxati va tovarlar berilgan. Har bir tovar uchun mos
kategoriyani tanla. Mos kategoriya yo'q bo'lsa — yangi kategoriya taklif qil: ko'plikdagi umumiy tur nomi
(brend/model emas, masalan "Gaz plitalar"), o'zbekcha (lotin) va ruscha, hamda bo'limlardan biri
(parent_slug).
Bir xil turdagi tovarlarga bir xil yangi nom ber. Boshqa turdagi kategoriyaga qo'yma.

{context}

Tovarlar:
{items}

Faqat JSON qaytar:
{{"<id>": {{"category_slug": "<slug>"}},
 "<id>": {{"new_category": {{"name_uz": "...", "name_ru": "...", "parent_slug": "..."}}}}}}
"""


def categorize_batch(batch: CardBatch, *, only_missing: bool = True, chunk: int = 40) -> dict:
    """Tekshirishdagi kartochkalar kategoriyasini AI bilan aniqlash (kategoriyasizlar yoki hammasi)."""
    drafts = [
        d
        for d in batch.drafts.filter(status=D.READY).order_by("id")
        if not only_missing or not d.result.get("category_slug")
    ]
    return categorize_drafts(drafts, chunk=chunk)


def categorize_drafts(drafts: list[CardDraft], *, chunk: int = 40) -> dict:
    ctx = catalog_context()
    lines = ["Kategoriyalar:"] + [f"- {c['slug']} ({c['name']})" for c in ctx]
    lines.insert(0, "Bo'limlar (parent_slug uchun): " + ", ".join(f"{s} ({n})" for s, n in _roots()))
    context = "\n".join(lines)
    stats = {"total": len(drafts), "matched": 0, "new": 0, "unchanged": 0}
    for i in range(0, len(drafts), chunk):
        part = drafts[i : i + chunk]
        items = "\n".join(
            f"{d.id}: {(d.result.get('name') or {}).get('uz') or d.query}"
            + (
                f" ({d.result.get('brand')} {d.result.get('model_code')})"
                if d.result.get("model_code")
                else ""
            )
            for d in part
        )
        _check_limit()
        call = AiCall(provider=client.provider() or "-", model=client.model_name()[:64])
        try:
            res = client.generate(
                CATEGORIZE_PROMPT.format(context=context, items=items), search=False, expect_json=True
            )
            _fill_call(call, res)
        finally:
            call.save()
        answer = client.extract_json(res.text)
        if not isinstance(answer, dict):
            continue
        for d in part:
            value = answer.get(str(d.id))
            if not isinstance(value, dict):
                stats["unchanged"] += 1
                continue
            slug = str(value.get("category_slug") or "")
            new = None
            if slug not in {c["slug"] for c in ctx}:
                slug, new = _match_new_category(value.get("new_category"), ctx)
            if not slug and not new:
                stats["unchanged"] += 1
                continue
            result = {**d.result, "category_slug": slug, "new_category": new}
            if slug != d.result.get("category_slug"):
                result["attributes"] = {}  # boshqa kategoriya xususiyatlari mos kelmaydi
            d.result = result
            d.warnings = [w for w in d.warnings if "kategoriya" not in w.lower()]
            if new:
                d.warnings.insert(
                    0, f"AI yangi kategoriya taklif qildi: «{new['name']['uz']}» (nashrda yaratiladi)."
                )
            d.save(update_fields=["result", "warnings", "updated_at"])
            stats["new" if new else "matched"] += 1
    return stats


# --- Avto-tuzatish: kartochkadagi muammolarni topib, o'zi tuzatadi ---
IMAGE_WARNING_MARKS = (
    "Rasm olinmadi",
    "Rasm juda kichik",
    "Rasm yaroqsiz",
    "Rasm ochilmadi",
    "Avto-tuzatish",
    "AI rasmlarni",
)


def recover_images(draft: CardDraft, have: list[str]) -> tuple[list[str], list[str]]:
    """Rasm topish (bepul): mavjudlari + tovar sahifasi (havola), manbalar sahifalari (schema.org va
    sahifadagi rasmlar) + model kodi bo'yicha rasm qidiruvi. Har biri "shu tovarnikimi" deb baholanadi,
    yuklab tekshiriladi va ko'ruvchi AI tasdiqlaydi (choose_images)."""
    from . import image_match, page_hints, research

    r = draft.result
    target, label, kind = _target(r, draft.query), _label(r, draft.query), _kind(r)
    own_url = draft.raw.get("url") or ""
    own_hints = draft.raw.get("hints") or {}
    cands = [image_match.Cand(u, "have") for u in have]
    cands += [
        image_match.Cand(u, "ownpage" if own_hints.get("images_guess") else "own", page=own_url)
        for u in own_hints.get("images", [])
        if isinstance(u, str)
    ]
    pages = [(own_url, "")] if own_url else []
    pages += [
        (s["uri"], str(s.get("title") or ""))
        for s in (r.get("sources") or [])[:3]
        if isinstance(s, dict) and s.get("uri")
    ]
    for i, (url, title) in enumerate(dict(pages).items()):
        hints = page_hints.fetch(url)
        page_imgs = research.read_page_full(url, limit=100)[1] if i < 2 else []  # brauzerda o'qish sekinroq
        for c in research.page_candidates(url, title, hints, page_imgs):
            if url == own_url:
                c["origin"] = "own" if c["origin"] == "main" else "ownpage"
            cands.append(image_match.Cand(**c))
    if r.get("model_code"):
        q = " ".join(x for x in (r.get("brand"), r.get("model_code")) if x)
        cands += [
            image_match.Cand(u, "search")
            for u in research.image_search(q, r["model_code"], brand=r.get("brand") or "")[:8]
        ]
    report = dict(r.get("image_report") or {})
    picked, warns = choose_images(target, cands, draft=draft, label=label, kind=kind, report=report)
    if len(picked) < 2 and settings.AI_CARDS.get("FREE_RESEARCH"):
        # Veb-qidiruv: topilgan do'kon sahifalarining o'z rasmlari (schema.org / og:image / sahifa rasmlari).
        q = " ".join(x for x in (r.get("brand"), r.get("model_code") or (r.get("name") or {}).get("uz")) if x)
        found = research.collect(q or draft.query, brand=r.get("brand") or "")
        known = {c.url for c in cands}
        fresh = [c for c in _cands_from_research(found) if c.url not in known]
        if fresh:
            more, warns2 = choose_images(
                target,
                [*(image_match.Cand(u, "have") for u in picked), *fresh],
                draft=draft,
                label=label,
                kind=kind,
                report=report,
            )
            if len(more) > len(picked):
                picked = more
            warns += warns2
    r["image_report"] = report  # chaqiruvchi (generate / autofix) natija bilan birga saqlaydi
    return picked, warns


def ai_image_urls(draft: CardDraft) -> list[str]:
    """Internet qidiruvli AI'dan rasm havolalari (xato bo'lsa — bo'sh ro'yxat; kartochka buzilmaydi)."""
    r = draft.result
    name = " ".join(x for x in (r.get("brand"), (r.get("name") or {}).get("uz") or draft.query) if x)
    try:
        _check_limit()
    except ApiError:
        return []
    call = AiCall(provider=client.provider() or "-", model=client.model_name()[:64], draft=draft)
    try:
        res = client.generate(
            lambda search: (
                IMAGE_PROMPT.format(
                    name=name, model=f" (model: {r['model_code']})" if r.get("model_code") else ""
                )
                if search
                else None
            ),
            task="images",
            expect_json=True,
        )
        _fill_call(call, res)
        data = client.extract_json(res.text)
    except client.AiError as exc:
        call.ok = False
        logger.warning("Avto-tuzatish: AI rasm qidiruvi (%s): %s", draft.pk, exc.message)
        return []
    finally:
        call.save()
    urls = data.get("image_urls") if isinstance(data, dict) else None
    return [u for u in urls or [] if isinstance(u, str)]


def recheck_images(draft: CardDraft, result: dict) -> str:
    """Kartochkadagi AI hali ko'rmagan rasmlarni ko'ruvchi AI'ga tekshirtirish (yaratilganda limit tugagan
    bo'lsa). "Shu tovar emas" deganlari olib tashlanadi. Qaytaradi: nima qilingani (hech narsa — bo'sh)."""
    from . import vision

    report = dict(result.get("image_report") or {})
    seen = dict(report.get("seen") or {})
    images = [u for u in result.get("images") or [] if isinstance(u, str)]
    todo = [u for u in images if u not in seen][: vision.MAX_IMAGES]
    if not todo or not vision.enabled():
        return ""
    fetched, _ = _probe_images(todo)
    res = verify_images(draft, _label(result, draft.query), _kind(result), fetched)
    if res is None:
        report["vision_error"] = vision.last_error()
        result["image_report"] = report
        return ""
    bad = set()
    for f, verdict, note in zip(fetched, res.verdicts, res.notes, strict=False):
        if verdict is False:
            bad.add(f.source)
        elif verdict:
            seen[f.source] = note or "ok"
    result["images"] = [u for u in images if u not in bad]
    report.update(vision=res.model, seen=seen, ai_removed=int(report.get("ai_removed") or 0) + len(bad))
    report.pop("vision_error", None)
    result["image_report"] = report
    if bad:
        return f"AI rasmlarni ko'rdi: {len(bad)} tasi shu tovar emas — olib tashlandi"
    return "AI rasmlarni ko'rib tasdiqladi"


def autofix(draft: CardDraft) -> dict:
    """Bitta kartochka: xato — qayta yaratish; rasm < 2 — rasm topish; kategoriya yo'q — AI aniqlaydi.

    Natija: {"actions": [...], "status": ...}. Kartochkaga "Avto-tuzatish: ..." eslatmasi yoziladi.
    """
    actions: list[str] = []
    raw = {**draft.raw, "_autofix": timezone.now().isoformat()}
    CardDraft.objects.filter(pk=draft.pk).update(raw=raw)
    draft.raw = raw
    if draft.status == D.FAILED:
        draft = generate(reset(draft))
        actions.append(
            "qayta yaratildi"
            if draft.status == D.READY
            else f"qayta yaratildi — {draft.get_status_display()}"
        )
        if draft.status != D.READY:
            return {"actions": actions, "status": draft.status}
    if draft.status != D.READY:
        return {"actions": ["tekshirishdagi kartochka emas — o'tkazib yuborildi"], "status": draft.status}

    result = dict(draft.result)
    if note := recheck_images(draft, result):
        actions.append(note)
    draft.result = result  # keyingi qadamlar (rasm topish) yangilangan hisobot bilan ishlaydi
    have = list(result.get("images") or [])
    image_note = ""
    if len(have) < 2:
        picked, warns = recover_images(draft, have)
        if draft.result.get("image_report"):
            result["image_report"] = draft.result["image_report"]
        if len(picked) <= len(have):
            # Bepul yo'l topmadi — internetdan qidira oladigan AI (1 so'rov), "Rasm topish" kabi.
            ai_urls = ai_image_urls(draft)
            if ai_urls:
                from . import image_match

                more, warns2 = choose_images(
                    _target(result, draft.query),
                    [
                        *(image_match.Cand(u, "have") for u in picked),
                        *(image_match.Cand(u, "ai_search") for u in ai_urls),
                    ],
                    draft=draft,
                    label=_label(result, draft.query),
                    kind=_kind(result),
                )
                picked, warns = (
                    (more, warns + warns2) if len(more) > len(picked) else (picked, warns + warns2)
                )
        if len(picked) > len(have):
            result["images"] = picked
            actions.append(f"rasm: {len(have)} → {len(picked)} ta")
        else:
            reasons = sorted({w.split(":")[0].replace("Rasm olinmadi — ", "") for w in warns})[:3]
            image_note = "rasm topilmadi" + (f" ({', '.join(reasons)})" if reasons else "")
            actions.append(image_note)
    # Og'irlik/o'lchamni xususiyatlardan ajratish; yetishmaganini to'ldiruvchi AI so'rovi bilan olish.
    from . import smart

    filled = smart.enrich(result)
    if settings.AI_CARDS.get("REFINE", True):
        filled += refine(draft, result, {})
        smart.enrich(result)
    if filled:
        actions.append("to'ldirildi: " + ", ".join(dict.fromkeys(filled)))
    draft.result = result
    draft.warnings = [w for w in draft.warnings if not w.startswith(IMAGE_WARNING_MARKS)]
    draft.save(update_fields=["result", "warnings", "updated_at"])

    if not result.get("category_slug") and not result.get("new_category"):
        try:
            stats = categorize_drafts([draft])
            actions.append(
                "kategoriya aniqlandi" if stats["matched"] or stats["new"] else "kategoriya aniqlanmadi"
            )
        except client.AiError as exc:
            actions.append(f"kategoriya: AI ishlamadi ({exc.message[:80]})")
        draft.refresh_from_db()
    if not actions:
        actions.append("muammo topilmadi")
    draft.warnings = [f"Avto-tuzatish: {'; '.join(actions)}.", *draft.warnings][:30]
    draft.save(update_fields=["warnings", "updated_at"])
    return {"actions": actions, "status": draft.status}


def needs_autofix(d: CardDraft) -> bool:
    if d.status == D.FAILED:
        return True
    from . import smart

    r = d.result or {}
    if d.status != D.READY:
        return False
    if len(r.get("images") or []) < 2 or not (r.get("category_slug") or r.get("new_category")):
        return True
    if (r.get("image_report") or {}).get("vision_error"):
        return True  # rasmlarni AI ko'ra olmagan (limit) — qayta tekshiriladi
    return bool({i["code"] for i in smart.quality(r)["issues"]} & smart.REFINABLE)


def autofix_batch(batch: CardBatch, *, limit: int = 5) -> dict:
    """Muammoli kartochkalarni navbat bilan tuzatish (har chaqiruvda `limit` tasi; bir marta urinilganlari
    qayta olinmaydi). UI `remaining` 0 bo'lguncha chaqiradi."""
    todo = [
        d
        for d in batch.drafts.filter(status__in=[D.READY, D.FAILED]).order_by("id")
        if needs_autofix(d) and not d.raw.get("_autofix")
    ]
    done = []
    for d in todo[:limit]:
        done.append({"id": d.id, "row_number": d.row_number, **autofix(d)})
    return {"fixed": done, "remaining": max(len(todo) - limit, 0)}


def create_proposed_category(draft: CardDraft) -> CardDraft:
    """AI taklif qilgan yangi kategoriyani hozir yaratish (yoki bir xil nomlisini olish) va tanlash."""
    from apps.catalog.services import find_or_create_category

    if draft.status != D.READY:
        raise CardError("draft_not_ready", "Faqat tekshirish kutilayotgan kartochkada.")
    nc = (draft.result or {}).get("new_category")
    if not nc:
        raise ApiError("no_proposal", "Bu kartochkada yangi kategoriya taklifi yo'q.")
    category, _created = find_or_create_category(nc["name"], nc.get("parent_slug", ""))
    draft.result = {**draft.result, "category_slug": category.slug, "new_category": None, "attributes": {}}
    draft.warnings = [w for w in draft.warnings if "kategoriya" not in w.lower()]
    draft.save(update_fields=["result", "warnings", "updated_at"])
    return draft
