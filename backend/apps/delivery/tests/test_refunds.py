"""Qaytarish siyosati:
- eshikda ko'rib, sababini aytib rad etsa — yetkazish narxi ham qaytariladi;
- 3 urinishda bog'lanib bo'lmasa — yetkazish narxi qaytarilmaydi (tovar uchun to'langani qaytariladi).
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.backoffice.models import CashAccount, CashTransaction
from apps.core.settings_registry import set_setting

pytestmark = pytest.mark.django_db


def _refuse(courier_client, staff, route):
    sid = route["stops"][0]["id"]
    courier_client.post(reverse("courier-stop-start", args=[sid]))
    r = courier_client.post(
        reverse("courier-stop-refuse", args=[sid]), {"reason": "Nuqson bor"}, format="json"
    )
    assert r.status_code == 200
    staff.post(reverse("admin-route-sheet-close", args=[route["id"]]))


def _fail_out(courier_client, staff, route):
    sid = route["stops"][0]["id"]
    courier_client.post(reverse("courier-stop-fail", args=[sid]), {"outcome": "no_answer"}, format="json")
    staff.post(reverse("admin-route-sheet-close", args=[route["id"]]))


def test_refused_cod_order_refunds_delivery_fee(make_order, issued_route, courier_client, staff):
    order = make_order("cash")
    assert order.paid_amount == Decimal("25000.00")
    _refuse(courier_client, staff, issued_route(order))
    order.refresh_from_db()
    assert order.status == "returned"
    assert order.refund_due == Decimal("25000.00") and order.payment_status == "refund_pending"


def test_refused_prepaid_order_refunds_everything(make_order, issued_route, courier_client, staff):
    order = make_order("payme")
    _refuse(courier_client, staff, issued_route(order))
    order.refresh_from_db()
    assert order.refund_due == order.total == Decimal("3025000.00")


def test_unreachable_cod_order_keeps_delivery_fee(make_order, issued_route, courier_client, staff):
    set_setting("delivery_max_attempts", 1)
    order = make_order("cash")
    _fail_out(courier_client, staff, issued_route(order))
    order.refresh_from_db()
    assert order.status == "returned"
    assert order.refund_due == 0 and order.payment_status == "partially_paid"


def test_unreachable_prepaid_order_refunds_goods_only(make_order, issued_route, courier_client, staff):
    set_setting("delivery_max_attempts", 1)
    order = make_order("payme")
    _fail_out(courier_client, staff, issued_route(order))
    order.refresh_from_db()
    assert order.refund_due == Decimal("3000000.00") and order.payment_status == "refund_pending"


def test_finance_records_refund(make_order, issued_route, courier_client, staff, staff_client):
    order = make_order("payme")
    _refuse(courier_client, staff, issued_route(order))
    bank = CashAccount.objects.create(name="Bank", kind="bank")
    r = staff.get(reverse("admin-order-list"), {"payment_status": "refund_pending"})
    assert [o["number"] for o in r.json()["results"]] == [order.number]

    url = reverse("admin-order-refund", args=[order.number])
    assert staff_client("warehouse").post(url, {"account": bank.pk}, format="json").status_code == 403
    r = staff.post(url, {"account": bank.pk, "amount": "4000000"}, format="json")
    assert r.json()["error"]["code"] == "wrong_amount"
    r = staff.post(url, {"account": bank.pk}, format="json")
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["payment_status"] == "refunded" and body["refund_due"] == "0.00"
    assert body["refunded_amount"] == "3025000.00"
    tx = CashTransaction.objects.get(order=order)
    assert tx.direction == "out" and tx.category == "refund" and tx.amount == Decimal("3025000.00")
    assert staff.post(url, {"account": bank.pk}, format="json").json()["error"]["code"] == "nothing_to_refund"
