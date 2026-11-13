"""Kun tovari (vaqtli aksiya): boshlanganda narx almashadi, tugaganda qaytadi.

Alohida fon vazifasi shart emas: `maybe_sync()` savat, rasmiylashtirish va aksiyalar ro'yxati so'ralganda
chaqiriladi (keshdagi "keyingi chegara" vaqtigacha bazaga murojaat qilinmaydi).
"""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product, ProductVariant
from apps.catalog.services import change_price
from apps.core.exceptions import ApiError

from .models import Deal

_NEXT = "marketing:deals:next"
S = Deal.State


def _restore(deal: Deal) -> None:
    """Aksiya narxi hali turgan bo'lsa — avvalgi narx qaytariladi (xodim o'zgartirgan bo'lsa tegilmaydi)."""
    v = deal.variant
    if deal.base_price is not None and v.price == deal.price:
        old = deal.base_old_price if deal.base_old_price and deal.base_old_price > deal.base_price else None
        change_price(v, deal.base_price, old)


@transaction.atomic
def sync(now=None) -> int:
    """Muddati kelgan aksiyalarni boshlash va tugaganlarini yopish. Qaytaradi: o'zgargan aksiyalar soni."""
    now = now or timezone.now()
    changed = 0
    ending = Deal.objects.select_for_update().filter(state=S.ACTIVE, ends_at__lte=now)
    for deal in ending.select_related("variant"):
        _restore(deal)
        deal.state = S.ENDED
        deal.save(update_fields=["state", "updated_at"])
        changed += 1
    starting = Deal.objects.select_for_update().filter(state=S.SCHEDULED, starts_at__lte=now)
    for deal in starting.select_related("variant"):
        v = deal.variant
        if deal.ends_at <= now:
            deal.state = S.ENDED  # boshlanmasdan o'tib ketgan
        elif deal.price >= v.price:
            deal.state, deal.note = S.CANCELLED, "Tovar narxi aksiya narxidan past yoki teng bo'lib qolgan"
        else:
            deal.base_price, deal.base_old_price = v.price, v.old_price
            change_price(v, deal.price, max(v.price, v.old_price or Decimal("0")))
            deal.state = S.ACTIVE
        deal.save(update_fields=["state", "note", "base_price", "base_old_price", "updated_at"])
        changed += 1
    cache.delete(_NEXT)
    return changed


def maybe_sync() -> None:
    now = timezone.now()
    nxt = cache.get(_NEXT)
    if nxt is not None and now < nxt:
        return
    sync(now)
    bounds = [
        *Deal.objects.filter(state=S.ACTIVE).values_list("ends_at", flat=True),
        *Deal.objects.filter(state=S.SCHEDULED).values_list("starts_at", flat=True),
    ]
    horizon = now + timedelta(seconds=60)
    cache.set(_NEXT, min([*bounds, horizon]), 60)


def live():
    """Hozir davom etayotgan aksiyalar (tugashi yaqini oldin)."""
    maybe_sync()
    return (
        Deal.objects.filter(
            state=S.ACTIVE,
            ends_at__gt=timezone.now(),
            variant__is_active=True,
            variant__product__status=Product.Status.ACTIVE,
        )
        .select_related("variant__product")
        .order_by("ends_at", "id")
    )


@transaction.atomic
def create(*, variant: ProductVariant, price: Decimal, starts_at, ends_at, note: str = "") -> Deal:
    now = timezone.now()
    starts_at = starts_at or now
    if ends_at <= max(starts_at, now):
        raise ApiError("deal_dates", "Tugash vaqti boshlanishidan va hozirgi vaqtdan keyin bo'lishi kerak.")
    if ends_at - starts_at > timedelta(days=31):
        raise ApiError("deal_dates", "Aksiya muddati 31 kundan oshmasin.")
    if price <= 0 or price >= variant.price:
        raise ApiError(
            "deal_price", f"Aksiya narxi hozirgi narxdan ({int(variant.price)} so'm) past bo'lishi kerak."
        )
    clash = Deal.objects.filter(
        variant=variant, state__in=[S.SCHEDULED, S.ACTIVE], starts_at__lt=ends_at, ends_at__gt=starts_at
    )
    if clash.exists():
        raise ApiError("deal_overlap", "Bu tovar uchun shu vaqtda boshqa aksiya bor.", status_code=409)
    deal = Deal.objects.create(
        variant=variant, price=price, starts_at=starts_at, ends_at=ends_at, note=note[:200]
    )
    sync(now)  # hozir boshlanishi kerak bo'lsa — darhol narx almashadi
    deal.refresh_from_db()
    return deal


@transaction.atomic
def cancel(deal: Deal) -> Deal:
    deal = Deal.objects.select_for_update().select_related("variant").get(pk=deal.pk)
    if deal.state == S.ACTIVE:
        _restore(deal)
    if deal.state in (S.ACTIVE, S.SCHEDULED):
        deal.state = S.CANCELLED
        deal.save(update_fields=["state", "updated_at"])
    cache.delete(_NEXT)
    return deal
