"""AI kartochkalar: fayl → qoralamalar → Gemini → normallashtirish → xodim tasdig'i → katalog.

Gemini javobiga ishonilmaydi: kategoriya, xususiyat va qiymatlar faqat bizdagi ro'yxatdan qabul qilinadi,
qolganlari `warnings` ga yoziladi. Kartochka faqat xodim tasdiqlagach katalogga tushadi.
"""

import json
import logging
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
from .excel import ExcelError, read_rows
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
        columns, rows, currency = read_rows(data, settings.AI_CARDS["MAX_ROWS"])
    except ExcelError as exc:
        raise ApiError("bad_file", str(exc)) from exc
    prices = [r.price for r in rows if r.price is not None]
    rate = get_setting("usd_uzs_rate")
    return {
        "rows_total": len(rows),
        "columns": columns,
        "currency": currency,
        "with_price": len(prices),
        "price_min": str(min(prices)) if prices else None,
        "price_max": str(max(prices)) if prices else None,
        "usd_rate": str(rate) if rate is not None else None,
        "sample": [
            {
                "row": r.number,
                "name": r.name,
                "sku": r.sku,
                "price": str(r.price) if r.price is not None else None,
                "qty": r.qty,
            }
            for r in rows[:6]
        ],
    }


@transaction.atomic
def create_batch(
    *, file_name: str, data: bytes, user, currency: str | None = None, usd_rate=None, markup_percent=None
) -> CardBatch:
    try:
        columns, rows, detected = read_rows(data, settings.AI_CARDS["MAX_ROWS"])
    except ExcelError as exc:
        raise ApiError("bad_file", str(exc)) from exc
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
                raw=r.raw,
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
- name_uz: "Brend Model turi" ko'rinishida, qisqa.
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
    raw = "; ".join(f"{k}: {v}" for k, v in draft.raw.items())
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
    from collections import OrderedDict

    limit = limit or settings.AI_CARDS["MAX_IMAGES"]

    from .images import is_junk

    def clean(xs):
        return [
            u
            for u in dict.fromkeys(xs or [])
            if isinstance(u, str) and urlparse(u).scheme in ("http", "https") and not is_junk(u)
        ]

    main = clean(urls)
    rest = [u for u in clean(extra) if u not in main]
    checked, warnings = _probe_images([*main, *rest][:max_checks])
    seen, picked = set(), []
    for tier in (set(main), set(rest)):
        by_domain: OrderedDict[str, list[str]] = OrderedDict()
        for url, _area, digest in sorted((c for c in checked if c[0] in tier), key=lambda x: -x[1]):
            if digest in seen:
                continue
            seen.add(digest)
            by_domain.setdefault(urlparse(url).netloc.removeprefix("www."), []).append(url)
        while len(picked) < limit and any(by_domain.values()):
            for urls_ in by_domain.values():
                if urls_ and len(picked) < limit:
                    picked.append(urls_.pop(0))
    return picked, warnings


def check_images(urls: list[str]) -> tuple[list[str], list[str]]:
    """Faqat ochiladigan va yetarlicha katta (≥300 px) rasm havolalari qoldiriladi (tartib saqlanadi)."""
    checked, warnings = _probe_images(urls)
    return [u for u, _, _ in checked], warnings


def _probe_images(urls: list[str], referer: str = "") -> tuple[list[tuple[str, int, str]], list[str]]:
    """[(url, maydon px², sha256)] — ochiladigan, haqiqiy rasm, ≥300 px (kattaroq varianti bo'lsa — o'sha)."""
    import hashlib

    from . import images

    ok, warnings = [], []
    for url in urls:
        f = images.fetch_best(url, referer=referer)
        if not f.ok:
            warnings.append(f"Rasm olinmadi — {f.reason}: {url}")
            continue
        ok.append((f.url, f.area, hashlib.sha256(f.content).hexdigest()))
    return ok, warnings


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
    for d in batch.drafts.filter(pk__in=ids).select_related("batch").order_by("row_number"):
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
                brand = (draft.raw or {}).get("brand") or ""
                found["research"] = research.collect(draft.query, brand=str(brand))
        res = found["research"]
        return build_prompt(draft, ctx, False, "" if res.empty else research.as_prompt(res))

    return build


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
    _check_limit()
    ctx = catalog_context()
    found: dict = {}  # bepul tadqiqot natijasi (kerak bo'lsa bir marta)
    call = AiCall(provider=client.provider() or "-", model=client.model_name()[:64], draft=draft)
    try:
        res = None
        try:
            res = client.generate(
                _prompt_builder(draft, ctx, found),
                url_context=bool(draft.raw.get("url")),
                task="url" if draft.raw.get("url") else "card",
                expect_json=True,
            )
        finally:
            if res is not None:
                _fill_call(call, res)
            call.save()
        raw = client.extract_json(res.text)
    except client.AiError as exc:
        logger.warning("AI xatosi (kartochka %s): %s", draft.pk, exc.message)
        if exc.code == "not_configured":
            AiCall.objects.filter(pk=call.pk).delete()  # so'rov yuborilmadi — limitga kirmaydi
        else:
            AiCall.objects.filter(pk=call.pk).update(ok=False)
        if exc.code in client.SERVICE_ERRORS:
            # Qator navbatda qoladi; UI to'ldirishni to'xtatadi va sababni ko'rsatadi.
            status = 429 if exc.code == "rate_limited" else 503
            raise ApiError(f"ai_{exc.code}", exc.message, status_code=status) from exc
        draft.status, draft.error = D.FAILED, exc.message
        draft.save(update_fields=["status", "error", "updated_at"])
        return draft

    result, warnings = normalize(raw, ctx)
    if not res.sources and found.get("research"):
        res.sources = found["research"].sources
    result["sources"] = res.sources[:10]
    if not result["found"]:
        draft.status, draft.result, draft.warnings, draft.error = D.NOT_FOUND, result, [], ""
    else:
        # Sahifaning o'z rasmlari (schema.org / og:image) — Gemini topganlaridan oldin.
        hint_images = [u for u in (draft.raw.get("hints") or {}).get("images", []) if isinstance(u, str)]
        if found.get("research"):
            hint_images += found["research"].images
        found_images = []
        if settings.AI_CARDS.get("FREE_RESEARCH") and result.get("model_code"):
            # Rasm qidiruvi (bepul): shu model kodi yozilgan katta rasmlar — sahifa rasmlarini to'ldiradi.
            from . import research

            q = " ".join(x for x in (result.get("brand"), result.get("model_code")) if x)
            found_images = research.image_search(q, result["model_code"], brand=result.get("brand") or "")[:8]
        result["images"], img_warnings = pick_images([*hint_images, *result["images"]], extra=found_images)
        img_warnings = img_warnings[:3]
        warnings += img_warnings
        if result["model_code"] and Product.objects.filter(model_code__iexact=result["model_code"]).exists():
            warnings.insert(0, f"Katalogda {result['model_code']} modelli tovar allaqachon bor.")
        draft.status, draft.result, draft.warnings, draft.error = D.READY, result, warnings, ""
    draft.model_used = f"{res.provider}: {res.model}"[:64]
    if res.fallback_notes:
        draft.warnings = [*draft.warnings, *[f"Zaxira AI ishlatildi — {n}" for n in res.fallback_notes]][:30]
    draft.save(update_fields=["status", "result", "warnings", "error", "model_used", "updated_at"])
    return draft


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
    return batch.drafts.filter(status=D.PENDING).order_by("row_number").first()


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
    return ContentFile(f.content, name=f"ai.{f.ext}") if f.ok else None


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
    draft.status, draft.result, draft.warnings, draft.error = D.PENDING, {}, [], ""
    draft.save(update_fields=["status", "result", "warnings", "error", "updated_at"])
    return draft


# --- mavjud tovarlarga rasm topish ---
IMAGE_PROMPT = """Internetdan quyidagi tovarning rasmlarini top: "{name}"{model}.
Avval ishlab chiqaruvchining rasmiy sayti, keyin yirik do'konlar. Faqat aynan shu modelning rasmi bo'lsin.
Faqat JSON qaytar (```json ... ``` ichida): {{"image_urls": ["https://.../rasm.jpg"]}} — to'g'ridan-to'g'ri
rasm fayli havolalari (jpg/png/webp), oq fonlisi afzal, 5 tagacha. Topilmasa: {{"image_urls": []}}"""


IMAGE_PICK_PROMPT = """Tovar: "{name}"{model}.
Quyidagi rasm havolalari shu tovar haqidagi internet sahifalaridan olingan (qavsda — qaysi sahifadan).
Faqat aynan shu tovarning (shu modelning) fotosuratlarini tanla. Boshqa tovar, aksessuar, logotip, banner,
ikonka, reklama rasmi — yo'q. Ishonching komil bo'lmasa — olma.
{candidates}
Faqat JSON qaytar: {{"image_urls": ["<ro'yxatdagi havolalardan>"]}} — eng mosi birinchi, 6 tagacha."""


def select_relevant_images(name: str, model: str, candidates: list[tuple[str, str]]) -> list[str] | None:
    """AI (Groq va h.k.) tizim topgan rasmlardan aynan shu tovarnikini tanlaydi. AI ishlamasa — None
    (chaqiruvchi topilganlarni o'zgartirmasdan ishlatadi)."""
    urls = list(dict.fromkeys(u for u, _ in candidates))
    if len(urls) < 2:
        return None
    src = dict(candidates)
    listing = "\n".join(f"- {u} ({urlparse(src.get(u) or u).netloc})" for u in urls[:30])
    try:
        _check_limit()
    except ApiError:
        return None
    call = AiCall(provider=client.provider() or "-", model=client.model_name()[:64])
    try:
        res = client.generate(
            IMAGE_PICK_PROMPT.format(
                name=name, model=f" (model: {model})" if model else "", candidates=listing
            ),
            task="images",
            search=False,
            expect_json=True,
        )
        _fill_call(call, res)
        data = client.extract_json(res.text)
    except client.AiError as exc:
        call.ok = False
        logger.warning("AI rasm tanlash xatosi (%s): %s", name, exc.message)
        return None
    finally:
        call.save()
    picked = data.get("image_urls") if isinstance(data, dict) else None
    allowed = set(urls)
    return [u for u in picked or [] if u in allowed] if isinstance(picked, list) else None


def find_images(product: Product, *, max_images: int = 3) -> int:
    """Rasmsiz tovarga AI (internet qidiruvi) orqali rasm topib yuklash. Qaytaradi: yuklangan rasmlar soni."""
    if product.images.exists():
        return 0
    name = " ".join(x for x in [product.brand.name if product.brand else "", product.name.get("uz", "")] if x)
    # 1) Bepul yo'l: qidiruv + sahifalarning o'z rasmlari (schema.org / og:image) — AI so'rovisiz.
    if settings.AI_CARDS.get("FREE_RESEARCH"):
        from . import research

        found = research.collect(
            f"{name} {product.model_code}".strip(), brand=product.brand.name if product.brand else ""
        )
        cands = found.images
        chosen = select_relevant_images(name, product.model_code, [(u, "") for u in cands])
        if chosen:
            cands = chosen  # AI tanlagani (aynan shu tovar)
        if saved := _save_images(product, cands, max_images):
            return saved
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
    return _save_images(product, urls, max_images)


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
    return out


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
            for d in batch.drafts.order_by("row_number")
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
        for d in batch.drafts.filter(status=D.READY).order_by("row_number")
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
)


def recover_images(draft: CardDraft, have: list[str]) -> tuple[list[str], list[str]]:
    """Rasm topish (AI'siz, bepul): mavjudlari + tovar sahifasi (havola), manbalar sahifalari (schema.org va
    sahifadagi rasmlar) + model kodi bo'yicha rasm qidiruvi. Hammasi tekshiriladi, sifatlisi tanlanadi."""
    from . import page_hints, research

    r = draft.result
    cands = list(have) + [u for u in (draft.raw.get("hints") or {}).get("images", []) if isinstance(u, str)]
    pages = [draft.raw["url"]] if draft.raw.get("url") else []
    pages += [s.get("uri") for s in (r.get("sources") or [])[:3] if isinstance(s, dict) and s.get("uri")]
    for i, url in enumerate(dict.fromkeys(pages)):
        cands += [u for u in page_hints.fetch(url).get("images", []) if isinstance(u, str)]
        if i < 2:  # sahifani brauzerda o'qish sekinroq — faqat 2 tasi
            cands += research.read_page_full(url, limit=100)[1][:8]
    extra = []
    if r.get("model_code"):
        q = " ".join(x for x in (r.get("brand"), r.get("model_code")) if x)
        extra = research.image_search(q, r["model_code"], brand=r.get("brand") or "")[:8]
    # AI (Groq) topilganlardan aynan shu tovar rasmlarini tanlaydi — boshqa tovar rasmlari tushmasin.
    label = " ".join(x for x in (r.get("brand"), (r.get("name") or {}).get("uz") or draft.query) if x)
    if len(cands) + len(extra) > 2:
        chosen = select_relevant_images(label, r.get("model_code", ""), [(u, "") for u in [*cands, *extra]])
        if chosen:
            cands, extra = chosen, []
    picked, warns = pick_images(cands, extra=extra, max_checks=18)
    if len(picked) < 2 and settings.AI_CARDS.get("FREE_RESEARCH"):
        # Veb-qidiruv: topilgan do'kon sahifalarining o'z rasmlari (schema.org / og:image / sahifa rasmlari).
        q = " ".join(x for x in (r.get("brand"), r.get("model_code") or (r.get("name") or {}).get("uz")) if x)
        found = research.collect(q or draft.query, brand=r.get("brand") or "")
        more, warns2 = pick_images([*picked, *found.images], max_checks=18)
        if len(more) > len(picked):
            picked = more
        warns += warns2
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
    have = list(result.get("images") or [])
    image_note = ""
    if len(have) < 2:
        picked, warns = recover_images(draft, have)
        if len(picked) <= len(have):
            # Bepul yo'l topmadi — internetdan qidira oladigan AI (1 so'rov), "Rasm topish" kabi.
            ai_urls = ai_image_urls(draft)
            if ai_urls:
                more, warns2 = pick_images([*picked, *ai_urls])
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
    r = d.result or {}
    return d.status == D.READY and (
        len(r.get("images") or []) < 2 or not (r.get("category_slug") or r.get("new_category"))
    )


def autofix_batch(batch: CardBatch, *, limit: int = 5) -> dict:
    """Muammoli kartochkalarni navbat bilan tuzatish (har chaqiruvda `limit` tasi; bir marta urinilganlari
    qayta olinmaydi). UI `remaining` 0 bo'lguncha chaqiradi."""
    todo = [
        d
        for d in batch.drafts.filter(status__in=[D.READY, D.FAILED]).order_by("row_number")
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
