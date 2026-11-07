"""Yetkazish jarayoni: yig'ish → marshrut varag'i → eshik oldida natija → marshrutni yopish → naqd topshirish.

Holat o'tishlari faqat `apps.orders.state.transition` orqali (tarix va yon ta'sirlar o'sha yerda).
"""

from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.core.exceptions import ApiError
from apps.core.money import money
from apps.core.settings_registry import get_setting
from apps.inventory import services as inventory
from apps.inventory.models import SerialUnit
from apps.orders.models import Order, OrderStatus, OrderStatusHistory, PaymentStatus
from apps.orders.state import transition

from .models import (
    CashHandover,
    CodCollection,
    Courier,
    DeliveryAttempt,
    DoorPayment,
    HandoverAct,
    OrderItemSerial,
    RouteSheet,
    RouteStop,
    StopResult,
    Vehicle,
)

S = OrderStatus
ACTOR_STAFF = OrderStatusHistory.Actor.STAFF
ACTOR_COURIER = OrderStatusHistory.Actor.COURIER


class DeliveryError(ApiError):
    status_code = 409
    default_code = "delivery_error"


def _ref(order: Order):
    return ("order", order.pk)


# --- yig'ish (ombor) ---
def start_picking(order: Order, user) -> Order:
    return transition(order, S.PICKING, actor_type=ACTOR_STAFF, actor=user)


@transaction.atomic
def pack(order: Order, user, serials: dict[int, list[int]] | None = None) -> Order:
    """Qadoqlash. Seriyali tovarlarda har bir dona uchun IMEI/seriya raqam tanlanadi (skaner)."""
    serials = {int(k): v for k, v in (serials or {}).items()}
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != S.PICKING:
        raise DeliveryError("not_picking", 'Buyurtma "yig\'ilmoqda" holatida emas.')
    items = list(order.items.select_related("variant__product"))
    unknown = set(serials) - {i.id for i in items}
    if unknown:
        raise DeliveryError("unknown_item", "Buyurtmada bunday pozitsiya yo'q.", status_code=400)

    for item in items:
        ids = list(dict.fromkeys(serials.get(item.id, [])))
        if item.variant.product.serial_tracking == "none":
            if ids:
                raise DeliveryError(
                    "serials_not_tracked",
                    f"{item.sku}: bu tovar seriya raqam bilan hisoblanmaydi.",
                    status_code=400,
                )
            continue
        if len(ids) != item.qty:
            raise DeliveryError(
                "serials_count_mismatch",
                f"{item.sku}: {item.qty} ta dona uchun {item.qty} ta seriya raqam kerak.",
                status_code=400,
            )
        units = list(
            SerialUnit.objects.select_for_update()
            .filter(pk__in=ids, variant_id=item.variant_id, status=SerialUnit.Status.IN_STOCK)
            .order_by("id")
        )
        if len(units) != len(ids):
            raise DeliveryError(
                "serial_unavailable", f"{item.sku}: tanlangan seriya raqamlar omborda mavjud emas."
            )
        expected = inventory.reservation_warehouses("order", order.pk, item.variant_id)
        if Counter(u.warehouse_id for u in units) != Counter(expected):
            raise DeliveryError(
                "serial_wrong_warehouse",
                f"{item.sku}: donalar buyurtma band qilingan ombordan bo'lishi kerak.",
            )
        for u in units:
            wh = u.warehouse_id
            inventory.set_serial_status(
                u, SerialUnit.Status.RESERVED, warehouse_id=wh, ref=_ref(order), user=user
            )
            OrderItemSerial.objects.create(order_item=item, serial_unit=u, warehouse_id=wh)
    return transition(order, S.PACKED, actor_type=ACTOR_STAFF, actor=user)


def on_order_status(order: Order, previous: str, to: str) -> None:
    """orders.state yon ta'siri: seriyali donalar holati buyurtma bilan birga o'zgaradi."""
    links = list(OrderItemSerial.objects.filter(order_item__order=order).select_related("serial_unit"))
    if not links:
        return
    units = {
        u.pk: u
        for u in SerialUnit.objects.select_for_update().filter(pk__in=[x.serial_unit_id for x in links])
    }
    for link in links:
        unit = units[link.serial_unit_id]
        if to == S.HANDED_TO_COURIER and unit.status == SerialUnit.Status.RESERVED:
            inventory.set_serial_status(unit, SerialUnit.Status.SOLD, warehouse_id=None, ref=_ref(order))
        elif to == S.CANCELLED and unit.status == SerialUnit.Status.RESERVED:
            inventory.set_serial_status(
                unit, SerialUnit.Status.IN_STOCK, warehouse_id=link.warehouse_id, ref=_ref(order)
            )
        elif to == S.RETURNED and unit.status == SerialUnit.Status.SOLD:
            inventory.set_serial_status(
                unit, SerialUnit.Status.IN_STOCK, warehouse_id=link.warehouse_id, ref=_ref(order)
            )


# --- urinishlar ---
def failed_attempts(order: Order) -> int:
    return DeliveryAttempt.objects.filter(order=order, outcome__in=DeliveryAttempt.Outcome.failures()).count()


def max_attempts() -> int:
    return get_setting("delivery_max_attempts")


# --- marshrut varag'i (logist) ---
def create_route(*, courier: Courier, warehouse, date, user, comment: str = "") -> RouteSheet:
    if not courier.is_active:
        raise DeliveryError("courier_inactive", "Kuryer faol emas.", status_code=400)
    return RouteSheet.objects.create(
        courier=courier, warehouse=warehouse, date=date, comment=comment, created_by=user
    )


def _lock_route(route: RouteSheet, *statuses: str) -> RouteSheet:
    route = RouteSheet.objects.select_for_update().select_related("courier").get(pk=route.pk)
    if route.status not in statuses:
        raise DeliveryError(
            "route_wrong_status", f'Marshrut varag\'i "{route.get_status_display()}" holatida.'
        )
    return route


@transaction.atomic
def add_orders(route: RouteSheet, numbers: list[str], user) -> list[RouteStop]:
    route = _lock_route(route, RouteSheet.Status.DRAFT)
    numbers = list(dict.fromkeys(numbers))
    orders = {o.number: o for o in Order.objects.select_for_update().filter(number__in=numbers)}
    missing = [n for n in numbers if n not in orders]
    if missing:
        raise DeliveryError("order_not_found", f"Buyurtma topilmadi: {', '.join(missing)}", status_code=404)

    seq = route.stops.aggregate(m=Max("sequence"))["m"] or 0
    stops = []
    for n in numbers:
        order = orders[n]
        if order.status not in (S.PACKED, S.IN_TRANSIT):
            raise DeliveryError(
                "order_not_ready", f"{n}: faqat qadoqlangan yoki qayta yetkaziladigan buyurtma qo'shiladi."
            )
        if order.status == S.IN_TRANSIT and failed_attempts(order) >= max_attempts():
            raise DeliveryError("attempts_exhausted", f"{n}: urinishlar tugagan, tovar omborga qaytariladi.")
        if RouteStop.objects.filter(order=order, is_open=True).exists():
            raise DeliveryError("already_in_route", f"{n}: buyurtma boshqa ochiq marshrutda.")
        if order.delivery_vehicle == Vehicle.TRUCK and route.courier.vehicle != Vehicle.TRUCK:
            raise DeliveryError("truck_required", f"{n}: yirik tovar — yuk mashinali kuryer kerak.")
        if order.status == S.PACKED:
            whs = {
                wh
                for item in order.items.all()
                for wh in inventory.reservation_warehouses("order", order.pk, item.variant_id)
            }
            if whs - {route.warehouse_id}:
                raise DeliveryError(
                    "wrong_warehouse", f"{n}: tovar boshqa omborda — avval marshrut omboriga ko'chiring."
                )
        seq += 1
        stops.append(RouteStop.objects.create(route=route, order=order, sequence=seq))
    return stops


@transaction.atomic
def remove_stop(route: RouteSheet, stop: RouteStop) -> None:
    _lock_route(route, RouteSheet.Status.DRAFT)
    stop.delete()


@transaction.atomic
def issue_route(route: RouteSheet, user) -> RouteSheet:
    """Kuryer tovarlarni oldi: qadoqlangan buyurtmalar `handed_to_courier` (tovar ombordan chiqadi)."""
    route = _lock_route(route, RouteSheet.Status.DRAFT)
    stops = list(route.stops.select_related("order"))
    if not stops:
        raise DeliveryError("route_empty", "Marshrut varag'ida buyurtma yo'q.", status_code=400)
    if not route.courier.is_active:
        raise DeliveryError("courier_inactive", "Kuryer faol emas.", status_code=400)
    for stop in stops:
        order = stop.order
        if order.status == S.PACKED:
            transition(order, S.HANDED_TO_COURIER, actor_type=ACTOR_STAFF, actor=user, note=f"{route.number}")
        elif order.status != S.IN_TRANSIT:
            raise DeliveryError(
                "order_changed",
                f"{order.number}: holati o'zgargan ({order.get_status_display()}) — olib tashlang.",
            )
    route.status = RouteSheet.Status.ISSUED
    route.issued_at = timezone.now()
    route.issued_by = user
    route.save(update_fields=["status", "issued_at", "issued_by", "updated_at"])
    return route


@transaction.atomic
def close_route(route: RouteSheet, user) -> RouteSheet:
    """Kun oxiri: kuryer qaytgan tovarlarni omborga topshirdi.

    - borilmagan nuqtalar → `in_transit` (urinish hisoblanmaydi);
    - rad etilgan, yoki urinishlari tugagan buyurtmalar → `returned` (tovar omborga qaytadi);
    - qolgan yetkazilmaganlar `in_transit`da qoladi — keyingi marshrutga qo'shiladi.
    """
    route = _lock_route(route, RouteSheet.Status.ISSUED)
    limit = max_attempts()
    for stop in route.stops.select_for_update().select_related("order"):
        order = Order.objects.select_for_update().get(pk=stop.order_id)
        if stop.result == StopResult.PENDING:
            stop.result = StopResult.NOT_VISITED
            stop.finished_at = timezone.now()
            if order.status in (S.HANDED_TO_COURIER, S.OUT_FOR_DELIVERY):
                order = transition(order, S.IN_TRANSIT, actor_type=ACTOR_STAFF, actor=user, note="Borilmadi")
        if stop.result == StopResult.REFUSED and order.status == S.REFUSED_AT_DOOR:
            transition(
                order, S.RETURNED, actor_type=ACTOR_STAFF, actor=user, note=f"{route.number}: rad etilgan"
            )
        elif order.status == S.IN_TRANSIT and failed_attempts(order) >= limit:
            transition(
                order,
                S.RETURNED,
                actor_type=ACTOR_STAFF,
                actor=user,
                note=f"{limit} ta urinish muvaffaqiyatsiz",
            )
        stop.is_open = False
        stop.save(update_fields=["result", "finished_at", "is_open"])
    route.status = RouteSheet.Status.CLOSED
    route.closed_at = timezone.now()
    route.closed_by = user
    route.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    return route


# --- kuryer: eshik oldida ---
def amount_due_at_door(order: Order) -> Decimal:
    return money(max(order.total - order.paid_amount, Decimal("0")))


def _lock_stop(stop: RouteStop, courier: Courier) -> RouteStop:
    stop = RouteStop.objects.select_for_update().select_related("route").get(pk=stop.pk)
    if stop.route.courier_id != courier.pk:
        raise DeliveryError("not_found", "Topilmadi.", status_code=404)
    if stop.route.status != RouteSheet.Status.ISSUED or not stop.is_open:
        raise DeliveryError("route_not_active", "Marshrut faol emas.")
    if stop.result != StopResult.PENDING:
        raise DeliveryError("stop_finished", "Bu buyurtma bo'yicha natija allaqachon kiritilgan.")
    return stop


def _attempt(stop, courier, outcome, comment="", lat=None, lng=None) -> DeliveryAttempt:
    return DeliveryAttempt.objects.create(
        order_id=stop.order_id,
        stop=stop,
        courier=courier,
        outcome=outcome,
        comment=comment[:500],
        latitude=lat,
        longitude=lng,
    )


def _finish(stop: RouteStop, result: str) -> None:
    stop.result = result
    stop.finished_at = timezone.now()
    stop.save(update_fields=["result", "finished_at"])


def _sms(order: Order, text: str, code: str) -> None:
    from apps.notifications.services import send_sms

    send_sms(order.recipient_phone, text, template_code=code, user=order.user)


@transaction.atomic
def start_stop(stop: RouteStop, courier: Courier) -> RouteStop:
    """Kuryer mijozga yo'l oldi: `out_for_delivery`, mijozga SMS."""
    stop = _lock_stop(stop, courier)
    order = Order.objects.select_for_update().get(pk=stop.order_id)
    if order.status in (S.HANDED_TO_COURIER, S.IN_TRANSIT):
        transition(order, S.OUT_FOR_DELIVERY, actor_type=ACTOR_COURIER, actor=courier.user)
        _sms(
            order,
            f"Buyurtma {order.number}: kuryer yo'lda. Kuryer: {courier} {courier.user.phone}",
            "courier_on_way",
        )
    elif order.status != S.OUT_FOR_DELIVERY:
        raise DeliveryError("order_changed", f"Buyurtma holati: {order.get_status_display()}.")
    if not stop.started_at:
        stop.started_at = timezone.now()
        stop.save(update_fields=["started_at"])
    return stop


def _locked_out_for_delivery(stop: RouteStop) -> Order:
    order = Order.objects.select_for_update().get(pk=stop.order_id)
    if order.status != S.OUT_FOR_DELIVERY:
        raise DeliveryError("not_started", 'Avval "Yo\'lga chiqdim" tugmasini bosing.')
    return order


def _paid_at_door(order: Order, stop: RouteStop) -> bool:
    from apps.payments.models import Payment

    return Payment.objects.filter(
        order=order, status=Payment.Status.SUCCEEDED, performed_at__gte=stop.started_at
    ).exists()


@transaction.atomic
def deliver(
    stop: RouteStop,
    courier: Courier,
    *,
    door_payment: str,
    inspection: dict,
    received_by: str,
    comment: str = "",
    lat=None,
    lng=None,
) -> HandoverAct:
    """Mijoz tovarni ko'rib qabul qildi.

    Qolgan summa: naqd (kuryer qarziga yoziladi) yoki QR (oldin tushgan).
    """
    stop = _lock_stop(stop, courier)
    order = _locked_out_for_delivery(stop)
    due = amount_due_at_door(order)
    collected = Decimal("0")
    if due > 0:
        if door_payment != DoorPayment.CASH:
            raise DeliveryError(
                "payment_required",
                f"Mijoz hali {due} so'm to'lamagan: naqd oling yoki QR to'lovni kuting.",
                extra={"amount_due": str(due)},
            )
        collected = due
        CodCollection.objects.create(courier=courier, order=order, amount=due)
        order.paid_amount = money(order.paid_amount + due)
        order.payment_status = PaymentStatus.PAID
        order.save(update_fields=["paid_amount", "payment_status", "updated_at"])
    else:
        door_payment = DoorPayment.QR if _paid_at_door(order, stop) else DoorPayment.PREPAID

    serials = [
        {
            "sku": link.order_item.sku,
            "serial_number": link.serial_unit.serial_number,
            "imei1": link.serial_unit.imei1,
            "imei2": link.serial_unit.imei2,
        }
        for link in OrderItemSerial.objects.filter(order_item__order=order).select_related(
            "order_item", "serial_unit"
        )
    ]
    act = HandoverAct.objects.create(
        order=order,
        stop=stop,
        courier=courier,
        inspection=inspection,
        serials=serials,
        door_payment=door_payment,
        amount_collected=collected,
        received_by=received_by,
        comment=comment[:500],
    )
    _attempt(stop, courier, DeliveryAttempt.Outcome.DELIVERED, comment, lat, lng)
    _finish(stop, StopResult.DELIVERED)
    transition(order, S.DELIVERED, actor_type=ACTOR_COURIER, actor=courier.user, note=act.number)
    return act


@transaction.atomic
def refuse(
    stop: RouteStop, courier: Courier, *, reason: str, comment: str = "", lat=None, lng=None
) -> RouteStop:
    """Mijoz tovarni ko'rib, olmadi. Tovar marshrut yopilganda omborga qaytadi."""
    stop = _lock_stop(stop, courier)
    order = _locked_out_for_delivery(stop)
    _attempt(stop, courier, DeliveryAttempt.Outcome.REFUSED, f"{reason}. {comment}".strip(". "), lat, lng)
    _finish(stop, StopResult.REFUSED)
    transition(order, S.REFUSED_AT_DOOR, actor_type=ACTOR_COURIER, actor=courier.user, note=reason)
    return stop


@transaction.atomic
def fail(stop: RouteStop, courier: Courier, *, outcome: str, comment: str = "", lat=None, lng=None) -> dict:
    """Mijoz topilmadi / telefonni ko'tarmadi / boshqa vaqt so'radi. Qaytaradi: urinishlar soni va chegara."""
    if outcome not in DeliveryAttempt.Outcome.failures():
        raise DeliveryError("bad_outcome", "Noto'g'ri sabab.", status_code=400)
    stop = _lock_stop(stop, courier)
    order = Order.objects.select_for_update().get(pk=stop.order_id)
    if order.status not in (S.HANDED_TO_COURIER, S.OUT_FOR_DELIVERY, S.IN_TRANSIT):
        raise DeliveryError("order_changed", f"Buyurtma holati: {order.get_status_display()}.")
    _attempt(stop, courier, outcome, comment, lat, lng)
    _finish(stop, StopResult.FAILED)
    count, limit = failed_attempts(order), max_attempts()
    label = DeliveryAttempt.Outcome(outcome).label
    if order.status != S.IN_TRANSIT:
        transition(
            order,
            S.IN_TRANSIT,
            actor_type=ACTOR_COURIER,
            actor=courier.user,
            note=f"{label} ({count}/{limit})",
        )
    if count < limit:
        _sms(order, f"Buyurtma {order.number}: kuryer sizni topa olmadi. Qayta yetkazamiz.", "courier_failed")
    return {"attempts": count, "max_attempts": limit, "will_return": count >= limit}


# --- kuryer naqd puli ---
def outstanding(courier: Courier) -> Decimal:
    total = CodCollection.objects.filter(courier=courier, handover__isnull=True).aggregate(s=Sum("amount"))[
        "s"
    ]
    return money(total or 0)


@transaction.atomic
def accept_cash(*, courier: Courier, account, user, comment: str = "", collection_ids=None) -> CashHandover:
    """Kassir kuryerdan naqd pulni qabul qildi: kassa hisobiga kirim, kuryer qarzi yopiladi."""
    from apps.backoffice.models import CashAccount, CashTransaction
    from apps.backoffice.services import record_cash

    if account.kind != CashAccount.Kind.CASH:
        raise DeliveryError(
            "account_not_cash", "Kuryer naqd puli faqat naqd kassaga qabul qilinadi.", status_code=400
        )
    qs = CodCollection.objects.select_for_update().filter(courier=courier, handover__isnull=True)
    if collection_ids is not None:
        qs = qs.filter(pk__in=collection_ids)
    rows = list(qs.order_by("id"))
    if collection_ids is not None and len(rows) != len(set(collection_ids)):
        raise DeliveryError(
            "collection_unavailable", "Tanlangan yozuvlar topilmadi yoki allaqachon topshirilgan."
        )
    if not rows:
        raise DeliveryError("nothing_to_accept", "Kuryerda topshiriladigan naqd pul yo'q.")
    amount = money(sum(r.amount for r in rows))
    handover = CashHandover.objects.create(
        courier=courier, account=account, amount=amount, accepted_by=user, comment=comment[:255]
    )
    handover.refresh_from_db()
    tx = record_cash(
        account=account,
        direction=CashTransaction.Direction.IN,
        amount=amount,
        category=CashTransaction.Category.COURIER_COD,
        user=user,
        comment=f"{handover.number} — {courier} ({len(rows)} ta buyurtma)",
    )
    handover.cash_transaction = tx
    handover.save(update_fields=["cash_transaction", "updated_at"])
    CodCollection.objects.filter(pk__in=[r.pk for r in rows]).update(handover=handover)
    return handover
