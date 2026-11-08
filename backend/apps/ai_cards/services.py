"""AI kartochkalar: fayl → qoralamalar → Gemini → normallashtirish → xodim tasdig'i → katalog.

Gemini javobiga ishonilmaydi: kategoriya, xususiyat va qiymatlar faqat bizdagi ro'yxatdan qabul qilinadi,
qolganlari `warnings` ga yoziladi. Kartochka faqat xodim tasdiqlagach katalogga tushadi.
"""

import json
import logging
from decimal import Decimal, InvalidOperation
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

from . import client, gemini
from .excel import ExcelError, read_rows
from .models import AiCall, CardBatch, CardDraft

D = CardDraft.Status
logger = logging.getLogger(__name__)


class CardError(ApiError):
    status_code = 409
    default_code = "ai_card_error"


# --- fayl ---
@transaction.atomic
def create_batch(*, file_name: str, data: bytes, user) -> CardBatch:
    try:
        columns, rows, currency = read_rows(data, settings.AI_CARDS["MAX_ROWS"])
    except ExcelError as exc:
        raise ApiError("bad_file", str(exc)) from exc
    batch = CardBatch.objects.create(
        file_name=file_name[:255], columns=columns, rows_total=len(rows), currency=currency, created_by=user
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


def _format_context(ctx: list[dict]) -> str:
    lines = []
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
  "category_slug": "<quyidagi ro'yxatdan>",
  "name_uz": "Samsung RB38 muzlatkichi",
  "name_ru": "Холодильник Samsung RB38",
  "description_uz": "2-4 gap, faktlar, reklama so'zlarisiz, o'zbek lotin yozuvida",
  "description_ru": "2-4 предложения на русском",
  "warranty_months": 12,
  "weight_kg": 70.5,
  "dimensions_cm": {{"length": 60, "width": 66, "height": 203}},
  "is_bulky": true,
  "attributes": {{"<kod>": "<qiymat>"}},
  "image_urls": ["https://.../rasm.jpg"]
}}

Qoidalar:
- category_slug va attributes kodlari FAQAT quyidagi ro'yxatdan. enum uchun variant kodini yoz,
  number uchun faqat son, bool uchun true/false.
- name_uz: "Brend Model turi" ko'rinishida, qisqa.
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
    if slug not in by_slug:
        if slug:
            warnings.append(f"Kategoriya noto'g'ri ({slug}) — qo'lda tanlang.")
        slug = ""
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
        "images": images,
    }
    if not result["name"]["uz"]:
        warnings.append("O'zbekcha nom yo'q.")
    if result["confidence"] is not None and result["confidence"] < 0.6:
        warnings.append("Gemini ishonchi past — ma'lumotlarni diqqat bilan tekshiring.")
    return result, warnings


MIN_IMAGE_SIDE = 300  # px — kichik eskizlar (64x64 va h.k.) kartochkaga yaramaydi


def image_size(data: bytes) -> tuple[int, int] | None:
    """PNG/JPEG/GIF/WEBP sarlavhasidan o'lcham (kutubxonasiz). Aniqlanmasa — None."""
    import struct

    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", data[6:10])
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            if data[12:16] == b"VP8X":
                return (int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1)
            if data[12:16] == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if data[12:16] == b"VP8L":
                b = data[21:25]
                w = 1 + (((b[1] & 0x3F) << 8) | b[0])
                h = 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
                return w, h
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                    return w, h
                i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]
    except (struct.error, IndexError):
        return None
    return None


def check_images(urls: list[str]) -> tuple[list[str], list[str]]:
    """Faqat ochiladigan va yetarlicha katta (≥300 px) rasm havolalari qoldiriladi."""
    ok, warnings = [], []
    limit = settings.AI_CARDS["IMAGE_MAX_BYTES"]
    with gemini.client(timeout=15, follow_redirects=True) as c:
        for url in urls:
            try:
                r = c.get(url, headers={"User-Agent": "Mozilla/5.0 (catalog image check)"})
            except httpx.HTTPError:
                warnings.append(f"Rasm ochilmadi: {url}")
                continue
            ctype = r.headers.get("content-type", "")
            if r.status_code != 200 or not ctype.startswith("image/") or len(r.content) > limit:
                warnings.append(f"Rasm yaroqsiz: {url}")
                continue
            size = image_size(r.content)
            too_small = min(size) < MIN_IMAGE_SIDE if size else len(r.content) < 8000
            if too_small:
                warnings.append(f"Rasm juda kichik ({'x'.join(map(str, size)) if size else 'eskiz'}): {url}")
                continue
            ok.append(url)
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
    if currency == "USD" and (rate := get_setting("usd_uzs_rate")):
        return money(price * rate)
    return None


def _prompt_builder(draft: CardDraft, ctx: list[dict], found: dict):
    """Qidira oladigan AI uchun — oddiy prompt; qidira olmaydiganiga — bepul tadqiqot natijasi bilan."""
    from . import research

    def build(search: bool) -> str:
        if search or not settings.AI_CARDS.get("FREE_RESEARCH"):
            return build_prompt(draft, ctx, search)
        if "research" not in found:
            if draft.raw.get("url"):
                text = research.read_page(draft.raw["url"])
                found["research"] = research.Research(
                    pages=[{"url": draft.raw["url"], "title": "", "snippet": "", "hints": {}, "text": text}]
                    if text
                    else []
                )
            else:
                brand = (draft.raw or {}).get("brand") or ""
                found["research"] = research.collect(draft.query, brand=str(brand))
        res = found["research"]
        return build_prompt(draft, ctx, False, "" if res.empty else research.as_prompt(res))

    return build


def usage() -> dict:
    """Bugungi AI so'rovlar soni va limit (Toshkent vaqti bo'yicha kun)."""
    from apps.core.settings_registry import get_setting

    used, caps = client.used_today(), client.caps()
    return {
        "provider": client.provider(),
        "model": client.model_name(),
        "search": client.has_search(),
        "providers": [
            {**p.__dict__, "used_today": used.get(p.name, 0), "daily_cap": caps.get(p.name)}
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
            )
        finally:
            if res is not None:
                call.provider, call.model = res.provider, res.model[:64]
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
        merged = list(dict.fromkeys([*hint_images, *result["images"]]))[: settings.AI_CARDS["MAX_IMAGES"]]
        result["images"], img_warnings = check_images(merged)
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
    try:
        with gemini.client(timeout=20, follow_redirects=True) as c:
            r = c.get(url, headers={"User-Agent": "Mozilla/5.0 (catalog image import)"})
    except httpx.HTTPError:
        return None
    ctype = r.headers.get("content-type", "")
    if (
        r.status_code != 200
        or not ctype.startswith("image/")
        or len(r.content) > settings.AI_CARDS["IMAGE_MAX_BYTES"]
    ):
        return None
    ext = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(ctype.split(";")[0], "jpg")
    return ContentFile(r.content, name=f"ai.{ext}")


@transaction.atomic
def approve(draft: CardDraft, *, user, price, old_price=None, sku: str = "", publish: bool = True) -> Product:
    draft = CardDraft.objects.select_for_update().get(pk=draft.pk)
    if draft.status != D.READY:
        raise CardError("draft_not_ready", "Faqat tekshirish kutilayotgan kartochkani nashr qilish mumkin.")
    r = draft.result
    category = Category.objects.filter(slug=r.get("category_slug") or "", is_active=True).first()
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

    failed = []
    for i, url in enumerate(r.get("images") or []):
        content = _download(url)
        if content is None:
            failed.append(url)
            continue
        img = ProductImage(product=product, external_url=url[:500], alt={"uz": name["uz"]}, sort=i)
        img.file.save(content.name, content, save=False)
        img.save()
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
        if saved := _save_images(product, found.images, max_images):
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
            res = client.generate(prompt, task="images")
        finally:
            if res is not None:
                call.provider, call.model = res.provider, res.model[:64]
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
        content = _download(url)
        if content is None:
            continue
        img = ProductImage(
            product=product, external_url=url[:500], alt={"uz": product.name.get("uz", "")}, sort=i
        )
        img.file.save(content.name, content, save=False)
        img.save()
        saved += 1
    return saved


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
