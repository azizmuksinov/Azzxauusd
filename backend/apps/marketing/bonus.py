"""Bonus (keshbek): xariddan bonus yoziladi, keyingi xaridda tovarlar summasining bir qismi bonus bilan
to'lanadi.

1 bonus = 1 so'm. Bonus buyurtma YETKAZILGANDA yoziladi (bekor qilingan xaridga yozilmaydi); bonus bilan
to'langan buyurtma bekor qilinsa yoki qaytsa — sarflangan bonus qaytadi. Foizlar — sozlamalarda
(`bonus_earn_percent` bo'sh bo'lsa tizim o'chiq). Yetkazish narxi bonus bilan to'lanmaydi va bonus yozilmaydi.
"""

from decimal import ROUND_DOWN, Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum

from apps.core.exceptions import ApiError
from apps.core.settings_registry import get_setting

from .models import BonusEntry

K = BonusEntry.Kind
ZERO = Decimal("0")


def _whole(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_DOWN).quantize(Decimal("0.01"))


def earn_percent() -> Decimal:
    v = get_setting("bonus_earn_percent")
    return Decimal(v) if v is not None and Decimal(v) > 0 else ZERO


def enabled() -> bool:
    return earn_percent() > 0


def max_pay_percent() -> int:
    return max(0, min(int(get_setting("bonus_max_pay_percent")), 90))  # kamida 10% pul bilan to'lanadi


def balance(user) -> Decimal:
    if user is None or not getattr(user, "is_authenticated", False):
        return ZERO
    return BonusEntry.objects.filter(user=user).aggregate(s=Sum("amount"))["s"] or ZERO


def usable(user, goods: Decimal) -> Decimal:
    """Shu xaridda bonus bilan to'lash mumkin bo'lgan eng katta summa (to'liq so'm)."""
    if not enabled() or goods <= 0:
        return ZERO
    cap = goods * max_pay_percent() / Decimal("100")
    return _whole(max(min(balance(user), cap), ZERO))


def will_earn(goods: Decimal) -> Decimal:
    """Shu summadagi xariddan yoziladigan bonus (ma'lumot uchun)."""
    return _whole(goods * earn_percent() / Decimal("100")) if goods > 0 else ZERO


def spend(order) -> None:
    """Buyurtmada bonus sarfi (buyurtma tranzaksiyasi ichida chaqiriladi)."""
    if order.bonus_spent <= 0:
        return
    # Parallel ikki buyurtma bir xil bonusni sarflamasligi uchun foydalanuvchi qatori qulflanadi.
    get_user_model().objects.select_for_update().get(pk=order.user_id)
    if balance(order.user) < order.bonus_spent:
        raise ApiError(
            "bonus_changed", "Bonus balansingiz o'zgargan. Sahifani yangilab qayta urinib ko'ring.", 409
        )
    BonusEntry.objects.create(
        user=order.user, amount=-order.bonus_spent, kind=K.SPEND, order=order, note=f"Buyurtma {order.number}"
    )


def refund(order) -> None:
    """Buyurtma bekor qilindi yoki qaytdi: sarflangan bonus qaytariladi (bir marta)."""
    if order.bonus_spent <= 0:
        return
    BonusEntry.objects.get_or_create(
        order=order,
        kind=K.REFUND,
        defaults={
            "user": order.user,
            "amount": order.bonus_spent,
            "note": f"Buyurtma {order.number} bekor qilindi",
        },
    )


def earn(order) -> Decimal:
    """Buyurtma yetkazildi: pul bilan to'langan tovarlar summasidan bonus yoziladi (bir marta)."""
    percent = earn_percent()
    goods = order.subtotal - order.discount_total - order.bonus_spent
    amount = _whole(goods * percent / Decimal("100")) if percent > 0 and goods > 0 else ZERO
    if amount <= 0:
        return ZERO
    _, created = BonusEntry.objects.get_or_create(
        order=order,
        kind=K.EARN,
        defaults={
            "user": order.user,
            "amount": amount,
            "note": f"Buyurtma {order.number}: {percent.normalize()}%",
        },
    )
    if created:
        type(order).objects.filter(pk=order.pk).update(bonus_earned=amount)
        order.bonus_earned = amount
    return amount


@transaction.atomic
def adjust(user, amount: Decimal, note: str, by=None) -> BonusEntry:
    """Qo'lda tuzatish (administrator): musbat — qo'shish, manfiy — ayirish (balans manfiy bo'lmaydi)."""
    amount = _whole(amount) if amount > 0 else -_whole(-amount)
    if amount == 0:
        raise ApiError("validation_error", "Summa 0 bo'lmasin.")
    get_user_model().objects.select_for_update().get(pk=user.pk)
    if amount < 0 and balance(user) + amount < 0:
        raise ApiError("bonus_insufficient", "Xaridorda shuncha bonus yo'q.")
    return BonusEntry.objects.create(user=user, amount=amount, kind=K.ADJUST, note=note[:200], created_by=by)
