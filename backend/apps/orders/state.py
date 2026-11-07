"""Buyurtma statuslari mashinasi (docs/01-arxitektura.md, 3-bo'lim)."""

from django.db import transaction

from apps.core.exceptions import ApiError

from .models import Order, OrderStatus, OrderStatusHistory

S = OrderStatus

TRANSITIONS: dict[str, set[str]] = {
    S.CREATED: {S.PAID, S.COD_CONFIRMED, S.CANCELLED},
    S.PAID: {S.PICKING, S.CANCELLED},
    S.COD_CONFIRMED: {S.PICKING, S.CANCELLED},
    S.PICKING: {S.PACKED, S.CANCELLED},
    S.PACKED: {S.HANDED_TO_COURIER, S.CANCELLED},
    S.HANDED_TO_COURIER: {S.IN_TRANSIT, S.OUT_FOR_DELIVERY},
    S.IN_TRANSIT: {S.OUT_FOR_DELIVERY, S.RETURNED},
    S.OUT_FOR_DELIVERY: {S.DELIVERED, S.REFUSED_AT_DOOR, S.IN_TRANSIT},
    S.REFUSED_AT_DOOR: {S.RETURNED},
    S.DELIVERED: set(),
    S.RETURNED: set(),
    S.CANCELLED: set(),
}

# Xaridor o'zi bekor qila oladigan holatlar (qadoqlanguncha).
CUSTOMER_CANCELLABLE = {S.CREATED, S.PAID, S.COD_CONFIRMED, S.PICKING}


class InvalidTransition(ApiError):
    status_code = 409
    default_code = "invalid_transition"


def can_transition(current: str, to: str) -> bool:
    return to in TRANSITIONS.get(current, set())


@transaction.atomic
def transition(order: Order, to: str, *, actor_type: str, actor=None, note: str = "") -> Order:
    """Statusni o'zgartirish: qulflash, ruxsatni tekshirish, tarixga yozish, yon ta'sirlar."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not can_transition(order.status, to):
        raise InvalidTransition(message=f"'{order.status}' holatidan '{to}' holatiga o'tib bo'lmaydi.")
    previous = order.status
    order.status = to
    order.save(update_fields=["status", "updated_at"])
    OrderStatusHistory.objects.create(
        order=order, from_status=previous, to_status=to, actor_type=actor_type, actor=actor, note=note
    )
    _side_effects(order, previous, to)
    return order


def _side_effects(order: Order, previous: str, to: str) -> None:
    from apps.delivery.services import on_order_status
    from apps.inventory import services as inventory

    if to == S.CANCELLED:
        inventory.release("order", order.pk)
        on_order_status(order, previous, to)
        _set_refund(order, order.paid_amount)
    elif to == S.HANDED_TO_COURIER:
        inventory.commit("order", order.pk)
        on_order_status(order, previous, to)
    elif to == S.RETURNED:
        # Tovar omborga qaytdi.
        inventory.return_committed("order", order.pk)
        on_order_status(order, previous, to)
        if previous == S.REFUSED_AT_DOOR:
            # Mijoz eshikda ko'rib, sababini aytib rad etdi — yetkazish narxi ham qaytariladi.
            _set_refund(order, order.paid_amount)
        else:
            # Urinishlar tugadi (mijoz bilan bog'lanib bo'lmadi) — yetkazish narxi qaytarilmaydi,
            # tovar uchun to'langan summa qaytariladi.
            _set_refund(order, order.paid_amount - order.delivery_fee - order.lifting_fee)


def _set_refund(order: Order, amount) -> None:
    """Qaytarish siyosati (docs/01-arxitektura.md, 9a): summani moliya bo'limi kassa/bank orqali qaytaradi."""
    from apps.core.money import money

    from .models import PaymentStatus

    amount = money(min(max(amount, 0), order.paid_amount))
    order.refund_due = amount
    if amount > 0:
        order.payment_status = PaymentStatus.REFUND_PENDING
    order.save(update_fields=["refund_due", "payment_status", "updated_at"])
