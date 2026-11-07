"""Provayderdan qat'i nazar umumiy mantiq: to'lovni qayd etish, bekor qilish, buyurtma holatini yangilash."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ApiError
from apps.core.money import money
from apps.orders.models import Order, OrderStatus, PaymentStatus
from apps.orders.state import transition

from .models import Payment


class NotPayable(ApiError):
    status_code = 409
    default_code = "order_not_payable"
    default_detail = "Bu buyurtmani hozir to'lab bo'lmaydi."


def payable_at_door(order: Order) -> bool:
    """Eshikda to'lov buyurtmasi, kuryer mijoz oldida: qolgan summani Payme/Click QR orqali to'lash mumkin."""
    return order.is_cod and order.status == OrderStatus.OUT_FOR_DELIVERY


def amount_due(order: Order) -> Decimal:
    """Onlayn to'lanishi kerak bo'lgan summa minus allaqachon to'langan.

    Buyurtma yaratilganda — to'liq summa yoki avans (yetkazish narxi);
    kuryer eshik oldida bo'lganda (QR) — qolgan butun summa.
    """
    target = order.total if payable_at_door(order) else order.required_prepayment
    return money(max(target - order.paid_amount, Decimal("0")))


def check_payable(order: Order, amount: Decimal | None = None) -> None:
    """Provayder to'lovni boshlashidan oldin: buyurtma holati, muddati va summasi."""
    if order.status != OrderStatus.CREATED and not payable_at_door(order):
        raise NotPayable(message="Buyurtma to'lov kutilayotgan holatda emas.")
    if (
        order.status == OrderStatus.CREATED
        and order.payment_deadline
        and order.payment_deadline < timezone.now()
    ):
        raise NotPayable(message="To'lov muddati o'tgan.")
    due = amount_due(order)
    if due <= 0:
        raise NotPayable(message="Buyurtma allaqachon to'langan.")
    if amount is not None and money(amount) != due:
        raise ApiError("wrong_amount", f"Summa noto'g'ri: kutilgan {due}.")


@transaction.atomic
def mark_succeeded(payment: Payment) -> Payment:
    """Pul yechildi: buyurtmadagi to'langan summa oshadi; talab bajarilsa buyurtma keyingi holatga o'tadi.

    Idempotent: allaqachon SUCCEEDED bo'lsa hech narsa qilmaydi.
    """
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == Payment.Status.SUCCEEDED:
        return payment
    if payment.status != Payment.Status.PENDING:
        raise NotPayable(message="Bekor qilingan to'lovni bajarib bo'lmaydi.")
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if order.status != OrderStatus.CREATED and not payable_at_door(order):
        # Masalan, buyurtma bekor qilingan — pul yechilmasligi kerak (provayder tranzaksiyani bekor qiladi).
        raise NotPayable(message="Buyurtma to'lov kutilayotgan holatda emas.")

    payment.status = Payment.Status.SUCCEEDED
    payment.performed_at = timezone.now()
    payment.save(update_fields=["status", "performed_at", "updated_at"])

    order.paid_amount = money(order.paid_amount + payment.amount)
    order.payment_status = (
        PaymentStatus.PAID if order.paid_amount >= order.total else PaymentStatus.PARTIALLY_PAID
    )
    order.save(update_fields=["paid_amount", "payment_status", "updated_at"])

    if order.status == OrderStatus.CREATED and order.paid_amount >= order.required_prepayment:
        # Eshikda to'lov + avans (yetkazish narxi) to'landi — bu mijoz tasdig'i hisoblanadi.
        target = OrderStatus.COD_CONFIRMED if order.is_cod else OrderStatus.PAID
        order.payment_deadline = None
        order.save(update_fields=["payment_deadline", "updated_at"])
        transition(order, target, actor_type="provider", note=f"{payment.provider}: {payment.amount} so'm")
        _clear_reservation_expiry(order)
    return payment


def _clear_reservation_expiry(order: Order) -> None:
    from apps.inventory.models import Reservation

    Reservation.objects.filter(
        ref_type="order", ref_id=str(order.pk), status=Reservation.Status.ACTIVE
    ).update(expires_at=None)


@transaction.atomic
def mark_cancelled(payment: Payment, reason: int | None = None) -> Payment:
    """Bekor qilish. Yechilmagan — CANCELLED; yechilgan bo'lsa — REFUNDED va buyurtmadagi summa kamayadi."""
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status in (Payment.Status.CANCELLED, Payment.Status.REFUNDED):
        return payment
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    was_paid = payment.status == Payment.Status.SUCCEEDED
    payment.status = Payment.Status.REFUNDED if was_paid else Payment.Status.CANCELLED
    payment.cancelled_at = timezone.now()
    payment.cancel_reason = reason
    payment.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])
    if was_paid:
        order.paid_amount = money(max(order.paid_amount - payment.amount, Decimal("0")))
        order.payment_status = (
            PaymentStatus.PARTIALLY_PAID if order.paid_amount > 0 else PaymentStatus.REFUNDED
        )
        order.save(update_fields=["paid_amount", "payment_status", "updated_at"])
        if order.status in (
            OrderStatus.PAID,
            OrderStatus.COD_CONFIRMED,
            OrderStatus.PICKING,
            OrderStatus.PACKED,
        ):
            transition(
                order,
                OrderStatus.CANCELLED,
                actor_type="provider",
                note=f"{payment.provider}: to'lov qaytarildi",
            )
    return payment


def can_refund(payment: Payment) -> bool:
    """Provayder qaytarishi mumkinmi (Payme CancelTransaction state=2): tovar hali kuryerga berilmagan."""
    return payment.order.status in (
        OrderStatus.PAID,
        OrderStatus.COD_CONFIRMED,
        OrderStatus.PICKING,
        OrderStatus.PACKED,
        OrderStatus.CANCELLED,
    )
