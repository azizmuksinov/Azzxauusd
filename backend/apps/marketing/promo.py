"""Promokodlar: tekshirish va chegirma summasi. Chegirma faqat tovarlar summasiga (yetkazishga emas)."""

from decimal import ROUND_DOWN, Decimal

from django.utils import timezone

from apps.core.exceptions import ApiError

from .models import PromoCode


def _fail(message: str):
    raise ApiError("promo_invalid", message)


def used_count(promo: PromoCode, user=None) -> int:
    from apps.orders.models import Order, OrderStatus

    qs = Order.objects.filter(promo_code=promo.code).exclude(status=OrderStatus.CANCELLED)
    return (qs.filter(user=user) if user is not None else qs).count()


def discount_for(promo: PromoCode, subtotal: Decimal) -> Decimal:
    if promo.kind == PromoCode.Kind.PERCENT:
        amount = subtotal * promo.value / Decimal("100")
        if promo.max_discount is not None:
            amount = min(amount, promo.max_discount)
    else:
        amount = promo.value
    amount = min(amount, subtotal)
    return amount.quantize(Decimal("1"), rounding=ROUND_DOWN).quantize(Decimal("0.01"))


def validate(code: str, subtotal: Decimal, user=None) -> tuple[PromoCode, Decimal]:
    """(promokod, chegirma summasi). Yaroqsiz bo'lsa — ApiError("promo_invalid", sababi)."""
    code = (code or "").strip().upper()
    if not code:
        _fail("Promokodni kiriting.")
    promo = PromoCode.objects.filter(code=code).first()
    now = timezone.now()
    if promo is None or not promo.is_active:
        _fail("Bunday promokod yo'q.")
    if promo.starts_at and promo.starts_at > now:
        _fail("Promokod hali boshlanmagan.")
    if promo.ends_at and promo.ends_at <= now:
        _fail("Promokod muddati tugagan.")
    if subtotal < promo.min_subtotal:
        _fail(f"Promokod {int(promo.min_subtotal):,} so'mdan yuqori xaridga amal qiladi.".replace(",", " "))
    if promo.usage_limit is not None and used_count(promo) >= promo.usage_limit:
        _fail("Promokoddan foydalanish soni tugagan.")
    if promo.once_per_customer and user is not None and getattr(user, "is_authenticated", False):
        if used_count(promo, user) > 0:
            _fail("Siz bu promokoddan foydalangansiz.")
    amount = discount_for(promo, subtotal)
    if amount <= 0:
        _fail("Promokod bu savatga chegirma bermaydi.")
    return promo, amount
