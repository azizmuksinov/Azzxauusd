from decimal import Decimal

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
) -> ProductVariant:
    """Narxni o'zgartirish. Narxning yagona manbai — shu tizim; har o'zgarish tarixga yoziladi."""
    _validate(price, old_price)
    variant = ProductVariant.objects.select_for_update().get(pk=variant.pk)
    if variant.price == price and variant.old_price == old_price:
        return variant
    variant.price, variant.old_price = price, old_price
    variant.save(update_fields=["price", "old_price", "updated_at"])
    PriceHistory.objects.create(
        variant=variant, price=price, old_price=old_price, source=source, changed_by=user
    )
    return variant
