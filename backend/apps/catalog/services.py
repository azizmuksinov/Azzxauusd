from decimal import Decimal

from django.conf import settings
from django.db import transaction

from apps.core.exceptions import ApiError

from .models import PriceHistory, ProductVariant


def _validate(price: Decimal, old_price: Decimal | None) -> None:
    if price is None or price < 0:
        raise ApiError("invalid_price", "Narx manfiy bo'lishi mumkin emas.")
    if old_price is not None and old_price <= price:
        raise ApiError("invalid_price", "Eski (chizilgan) narx joriy narxdan katta bo'lishi kerak.")


@transaction.atomic
def change_price(
    variant: ProductVariant,
    price: Decimal,
    old_price: Decimal | None = None,
    *,
    source: str = PriceHistory.Source.MANUAL,
    user=None,
    lock: bool | None = None,
) -> ProductVariant:
    """Narxni o'zgartirish + tarix. Qo'lda (yoki Excel) o'zgartirilsa, sozlamaga ko'ra narx qulflanadi."""
    _validate(price, old_price)
    variant = ProductVariant.objects.select_for_update().get(pk=variant.pk)
    if lock is None:
        lock = source != PriceHistory.Source.ONEC and settings.CATALOG_MANUAL_PRICE_LOCKS
    changed = variant.price != price or variant.old_price != old_price
    variant.price, variant.old_price = price, old_price
    variant.price_locked = lock if source != PriceHistory.Source.ONEC else variant.price_locked
    variant.save(update_fields=["price", "old_price", "price_locked", "updated_at"])
    if changed:
        PriceHistory.objects.create(
            variant=variant, price=price, old_price=old_price, source=source, changed_by=user
        )
    return variant


def apply_1c_price(variant: ProductVariant, price: Decimal, old_price: Decimal | None = None) -> bool:
    """1C sinxroni uchun: qulflangan narxga tegmaydi. Qaytaradi: o'zgartirildimi."""
    if variant.price_locked and settings.CATALOG_MANUAL_PRICE_LOCKS:
        return False
    if old_price is not None and old_price <= price:
        old_price = None
    change_price(variant, price, old_price, source=PriceHistory.Source.ONEC)
    return True
