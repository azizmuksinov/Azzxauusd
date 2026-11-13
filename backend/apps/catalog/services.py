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


def unique_category_slug(name: str) -> str:
    from django.utils.text import slugify

    from .models import Category

    base = slugify(name)[:120] or "kategoriya"
    slug, n = base, 2
    while Category.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def find_or_create_category(name: dict, parent_slug: str = ""):
    """Nomi bo'yicha (o'zbekcha yoki ruscha, katta-kichik harfsiz) mavjud kategoriya, bo'lmasa — yangisi.

    AI taklif qilgan yangi kategoriya uchun: bir xil nomli ikkinchi tovar yangi kategoriya ochmaydi.
    """
    from .models import Category

    names = {str(v).strip().lower() for v in (name or {}).values() if v}
    if not names:
        raise ValueError("Kategoriya nomi bo'sh")
    for c in Category.objects.all():
        if names & {str(v).strip().lower() for v in c.name.values() if v}:
            if not c.is_active:
                c.is_active = True
                c.save(update_fields=["is_active", "updated_at"])
            return c, False
    parent = Category.objects.filter(slug=parent_slug).first() if parent_slug else None
    uz = name.get("uz") or next(iter(v for v in name.values() if v))
    clean = {k: str(v).strip()[:120] for k, v in name.items() if v}
    return Category.objects.create(
        name=clean, parent=parent, slug=unique_category_slug(uz), is_active=True
    ), True
