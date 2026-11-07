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
    from apps.inventory import services as inventory

    if to == S.CANCELLED:
        inventory.release("order", order.pk)
        if order.paid_amount > 0:
            # To'lovni qaytarish payments modulida (keyingi bosqich) bajariladi.
            from .models import PaymentStatus

            order.payment_status = PaymentStatus.REFUND_PENDING
            order.save(update_fields=["payment_status", "updated_at"])
    elif to == S.HANDED_TO_COURIER:
        inventory.commit("order", order.pk)
