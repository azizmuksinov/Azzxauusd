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
