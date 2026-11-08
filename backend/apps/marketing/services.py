import re
from decimal import ROUND_DOWN, Decimal

from django.db import transaction

from apps.catalog.models import PriceHistory, ProductVariant
from apps.catalog.services import change_price
from apps.core.exceptions import ApiError


def _variants(category_id=None, brand_id=None, product_ids=None):
    qs = ProductVariant.objects.filter(is_active=True, product__status="active")
    if category_id:
        qs = qs.filter(product__category_id=category_id) | qs.filter(product__category__parent_id=category_id)
    if brand_id:
        qs = qs.filter(product__brand_id=brand_id)
    if product_ids:
        qs = qs.filter(product_id__in=product_ids)
    return qs.distinct()


@transaction.atomic
def apply_discount(*, percent: int, user, category_id=None, brand_id=None, product_ids=None) -> int:
    """Chegirma: eski narx = asl narx, yangi narx = asl narx * (1 - foiz). Yaxlitlash — 1000 so'mgacha pastga.

    Allaqachon chegirmadagi variantda asl narx (old_price) saqlanadi — chegirmalar ustma-ust tushmaydi.
    """
    if not (1 <= percent <= 90):
        raise ApiError("bad_percent", "Chegirma 1% dan 90% gacha bo'lishi mumkin.")
    if not (category_id or brand_id or product_ids):
        raise ApiError("scope_required", "Kategoriya, brend yoki tovarlarni tanlang.")
    n = 0
    for v in _variants(category_id, brand_id, product_ids):
        base = v.old_price or v.price
        new = (base * (100 - percent) / 100 / 1000).quantize(Decimal("1"), rounding=ROUND_DOWN) * 1000
        if new <= 0 or new >= base:
            continue
        change_price(v, new, base, source=PriceHistory.Source.MANUAL, user=user)
        n += 1
    return n


@transaction.atomic
def remove_discount(*, user, category_id=None, brand_id=None, product_ids=None) -> int:
    """Chegirmani bekor qilish: narx = eski narx."""
    if not (category_id or brand_id or product_ids):
        raise ApiError("scope_required", "Kategoriya, brend yoki tovarlarni tanlang.")
    n = 0
    for v in _variants(category_id, brand_id, product_ids).filter(old_price__isnull=False):
        change_price(v, v.old_price, None, source=PriceHistory.Source.MANUAL, user=user)
        n += 1
    return n


# --- Sayt matnlari (admin paneldan boshqariladi) ---
def _l(uz: str = "", ru: str = "") -> dict:
    return {"uz": uz, "ru": ru}


HOME_SECTIONS = {
    "hero": "Bannerlar",
    "categories": "Kategoriyalar",
    "deals": "Chegirmalar",
    "popular": "Ommabop tovarlar",
    "recent": "Yaqinda ko'rilganlar",
}
INFO_PAGES = {
    "how-to-order": _l("Qanday buyurtma beriladi", "Как оформить заказ"),
    "delivery": _l("Yetkazish va to'lov", "Доставка и оплата"),
    "returns": _l("Qaytarish va kafolat", "Возврат и гарантия"),
    "about": _l("Biz haqimizda", "О нас"),
}
SITE_DEFAULTS: dict = {
    "store_name": "TexnoDo'kon",
    "city": _l("Toshkent", "Ташкент"),
    "phone": "",
    "email": "",
    "address": _l(),
    "working_hours": _l("Har kuni 9:00–21:00", "Ежедневно 9:00–21:00"),
    "socials": {"telegram": "", "instagram": "", "facebook": "", "youtube": ""},
    "announcement": {"enabled": False, "text": _l(), "link": "", "color": "#5b21b6"},
    "home_sections": [{"key": k, "enabled": True, "title": _l()} for k in HOME_SECTIONS],
    "footer_about": _l(),
    "pay_methods": "Payme · Click · Uzum Bank · Uzcard · Humo",
    "pages": {k: {"title": t, "body": _l()} for k, t in INFO_PAGES.items()},
}


def _clean(default, value, limit: int = 300):
    """Qiymatni standart tuzilishga moslash: noma'lum kalitlar tashlanadi, turlar tekshiriladi."""
    if isinstance(default, dict):
        value = value if isinstance(value, dict) else {}
        return {k: _clean(d, value.get(k, d), 8000 if k == "body" else limit) for k, d in default.items()}
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, str):
        return str(value if value is not None else "").strip()[:limit]
    return default


def _clean_sections(value) -> list[dict]:
    seen, out = set(), []
    for item in value if isinstance(value, list) else []:
        key = item.get("key") if isinstance(item, dict) else None
        if key in HOME_SECTIONS and key not in seen:
            seen.add(key)
            out.append(
                {
                    "key": key,
                    "enabled": bool(item.get("enabled", True)),
                    "title": _clean(_l(), item.get("title")),
                }
            )
    # Ro'yxatda yo'q bo'limlar oxiriga (yoqilgan holda) qo'shiladi.
    out += [{"key": k, "enabled": True, "title": _l()} for k in HOME_SECTIONS if k not in seen]
    return out


def site_content() -> dict:
    from .models import SiteContent

    obj = SiteContent.objects.filter(pk=1).first()
    data = obj.data if obj else {}
    cleaned = _clean({k: v for k, v in SITE_DEFAULTS.items() if k != "home_sections"}, data)
    cleaned["home_sections"] = _clean_sections(data.get("home_sections"))
    color = cleaned["announcement"]["color"]
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        cleaned["announcement"]["color"] = SITE_DEFAULTS["announcement"]["color"]
    return cleaned


def update_site_content(patch: dict) -> dict:
    """Berilgan bo'limlar almashtiriladi (yuqori darajadagi kalitlar bo'yicha), qolganlari saqlanadi."""
    from .models import SiteContent

    if not isinstance(patch, dict):
        raise ValueError("JSON obyekt kerak")
    current = site_content()
    current.update({k: v for k, v in patch.items() if k in SITE_DEFAULTS})
    SiteContent.objects.update_or_create(pk=1, defaults={"data": current})
    return site_content()
