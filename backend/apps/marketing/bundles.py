"""Birga arzonroq: asosiy tovar savatda bo'lsa, qo'shimcha tovarga chegirma.

Qoida: har bir asosiy tovar donasi bitta qo'shimcha tovar donasiga chegirma beradi; bitta qo'shimcha donaga
faqat bitta (eng katta) chegirma qo'llanadi. Chegirma to'liq so'mgacha pastga yaxlitlanadi.
"""

from decimal import ROUND_DOWN, Decimal

from apps.catalog.models import Product

from .models import Bundle


def _amount(price: Decimal, percent: Decimal) -> Decimal:
    return (price * percent / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_DOWN)


def cart_discount(lines) -> tuple[Decimal, list[dict]]:
    """(jami chegirma, tafsilotlar). `lines` — cart.services.CartLine ro'yxati."""
    usable = [ln for ln in lines if ln.problem != "unavailable"]
    qty_by_product: dict[int, int] = {}
    for ln in usable:
        qty_by_product[ln.variant.product_id] = qty_by_product.get(ln.variant.product_id, 0) + ln.item.qty
    if len(qty_by_product) < 2:
        return Decimal("0"), []
    ids = list(qty_by_product)
    bundles = list(
        Bundle.objects.filter(is_active=True, product_id__in=ids, extra_id__in=ids).order_by(
            "-discount_percent", "id"
        )
    )
    if not bundles:
        return Decimal("0"), []
    main_left = {}  # (asosiy tovar, qo'shimcha tovar) juftligi bo'yicha qolgan huquq
    total, details = Decimal("0"), []
    # Qo'shimcha tovar qatorlari: qimmat variant oldin (chegirma xaridor foydasiga).
    for ln in sorted(usable, key=lambda x: -x.unit_price):
        left = ln.item.qty
        for b in bundles:
            if left <= 0:
                break
            if b.extra_id != ln.variant.product_id:
                continue
            key = (b.product_id, b.extra_id)
            grant = main_left.setdefault(key, qty_by_product.get(b.product_id, 0))
            n = min(left, grant)
            if n <= 0:
                continue
            amount = _amount(ln.unit_price, b.discount_percent) * n
            main_left[key] = grant - n
            left -= n
            total += amount
            details.append(
                {
                    "item_id": ln.item.id,
                    "product_id": b.extra_id,
                    "with_product_id": b.product_id,
                    "percent": str(b.discount_percent.normalize()),
                    "qty": n,
                    "amount": str(amount),
                }
            )
    return total, details


def offers(product: Product) -> list[tuple[Bundle, Product]]:
    """Tovar sahifasi uchun: shu tovar bilan birga arzonroq olinadigan (sotuvdagi) tovarlar."""
    from apps.catalog.selectors import public_products

    bundles = list(Bundle.objects.filter(product=product, is_active=True))
    if not bundles:
        return []
    extras = {
        p.pk: p for p in public_products().filter(pk__in=[b.extra_id for b in bundles], available__gt=0)
    }
    return [(b, extras[b.extra_id]) for b in bundles if b.extra_id in extras]


def price_with(bundle: Bundle, extra_price: Decimal) -> Decimal:
    return extra_price - _amount(extra_price, bundle.discount_percent)
