import base64

import pytest
from django.urls import reverse

from apps.payments.models import Payment, WebhookLog
from apps.payments.providers.payme import TIMEOUT_MS, now_ms

pytestmark = pytest.mark.django_db

AUTH = "Basic " + base64.b64encode(b"Paycom:payme-test-key").decode()


def rpc(api_client, method, params, auth=AUTH):
    resp = api_client.post(
        reverse("webhook-payme"),
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        format="json",
        HTTP_AUTHORIZATION=auth,
    )
    assert resp.status_code == 200
    return resp.json()


def acc(order):
    return {"order_id": order.number}


def test_auth_required(api_client, make_order):
    order = make_order()
    for bad in ["", "Basic " + base64.b64encode(b"Paycom:wrong").decode(), "Bearer x"]:
        r = rpc(api_client, "CheckPerformTransaction", {"amount": 302500000, "account": acc(order)}, auth=bad)
        assert r["error"]["code"] == -32504
    assert WebhookLog.objects.filter(signature_valid=False).count() == 3


def test_full_flow(api_client, make_order):
    order = make_order("payme")
    amount = 302500000  # 3 025 000 so'm tiyinda
    r = rpc(api_client, "CheckPerformTransaction", {"amount": amount, "account": acc(order)})
    assert r["result"]["allow"] is True
    items = r["result"]["detail"]["items"]
    assert items[0]["code"] == "12345678901234567" and items[-1]["title"] == "Yetkazib berish"
    assert sum(i["price"] * i["count"] for i in items) == amount

    t = now_ms()
    r = rpc(
        api_client, "CreateTransaction", {"id": "pm-1", "time": t, "amount": amount, "account": acc(order)}
    )
    assert r["result"]["state"] == 1
    # takroriy Create — o'sha javob
    assert (
        rpc(
            api_client,
            "CreateTransaction",
            {"id": "pm-1", "time": t, "amount": amount, "account": acc(order)},
        )["result"]["state"]
        == 1
    )
    # boshqa tranzaksiya — buyurtma band
    r2 = rpc(
        api_client, "CreateTransaction", {"id": "pm-2", "time": t, "amount": amount, "account": acc(order)}
    )
    assert r2["error"]["code"] == -31051

    r = rpc(api_client, "PerformTransaction", {"id": "pm-1"})
    assert r["result"]["state"] == 2 and r["result"]["perform_time"] > 0
    order.refresh_from_db()
    assert order.status == "paid" and order.payment_status == "paid" and order.paid_amount == 3025000
    # takroriy Perform — idempotent
    assert rpc(api_client, "PerformTransaction", {"id": "pm-1"})["result"]["state"] == 2
    order.refresh_from_db()
    assert order.paid_amount == 3025000

    check = rpc(api_client, "CheckTransaction", {"id": "pm-1"})["result"]
    assert check["state"] == 2 and check["create_time"] == t


@pytest.mark.parametrize(("amount", "code"), [(100, -31001), (302500001, -31001)])
def test_wrong_amount(api_client, make_order, amount, code):
    order = make_order()
    assert (
        rpc(api_client, "CheckPerformTransaction", {"amount": amount, "account": acc(order)})["error"]["code"]
        == code
    )


def test_unknown_order_and_method(api_client):
    assert (
        rpc(api_client, "CheckPerformTransaction", {"amount": 1, "account": {"order_id": "x"}})["error"][
            "code"
        ]
        == -31050
    )
    assert rpc(api_client, "Foo", {})["error"]["code"] == -32601
    assert rpc(api_client, "CheckTransaction", {"id": "nope"})["error"]["code"] == -31003


def test_cod_prepayment_only_delivery(api_client, make_order):
    """Naqd buyurtma: Payme orqali faqat yetkazish narxi (25 000) to'lanadi, keyin buyurtma tasdiqlanadi."""
    order = make_order("cash")
    assert (
        rpc(api_client, "CheckPerformTransaction", {"amount": 302500000, "account": acc(order)})["error"][
            "code"
        ]
        == -31001
    )
    r = rpc(api_client, "CheckPerformTransaction", {"amount": 2500000, "account": acc(order)})
    assert [i["title"] for i in r["result"]["detail"]["items"]] == ["Yetkazib berish"]
    rpc(
        api_client,
        "CreateTransaction",
        {"id": "pm-c", "time": now_ms(), "amount": 2500000, "account": acc(order)},
    )
    rpc(api_client, "PerformTransaction", {"id": "pm-c"})
    order.refresh_from_db()
    assert order.status == "cod_confirmed" and order.payment_status == "partially_paid"
    assert order.paid_amount == 25000 and order.cod_amount == 3000000 and order.payment_deadline is None


def test_cancel_before_perform(api_client, make_order):
    order = make_order()
    rpc(
        api_client,
        "CreateTransaction",
        {"id": "pm-x", "time": now_ms(), "amount": 302500000, "account": acc(order)},
    )
    r = rpc(api_client, "CancelTransaction", {"id": "pm-x", "reason": 3})
    assert r["result"]["state"] == -1
    assert rpc(api_client, "PerformTransaction", {"id": "pm-x"})["error"]["code"] == -31008
    order.refresh_from_db()
    assert order.status == "created"  # buyurtma hali to'lov kutmoqda — boshqa usul bilan to'lash mumkin


def test_cancel_after_perform_refunds_and_cancels_order(api_client, make_order):
    order = make_order()
    rpc(
        api_client,
        "CreateTransaction",
        {"id": "pm-r", "time": now_ms(), "amount": 302500000, "account": acc(order)},
    )
    rpc(api_client, "PerformTransaction", {"id": "pm-r"})
    r = rpc(api_client, "CancelTransaction", {"id": "pm-r", "reason": 5})
    assert r["result"]["state"] == -2
    order.refresh_from_db()
    assert order.status == "cancelled" and order.paid_amount == 0 and order.payment_status == "refunded"


def test_cannot_cancel_after_handover(api_client, make_order):
    from apps.orders.state import transition

    order = make_order()
    rpc(
        api_client,
        "CreateTransaction",
        {"id": "pm-h", "time": now_ms(), "amount": 302500000, "account": acc(order)},
    )
    rpc(api_client, "PerformTransaction", {"id": "pm-h"})
    order.refresh_from_db()
    for s in ["picking", "packed", "handed_to_courier"]:
        order = transition(order, s, actor_type="staff")
    assert rpc(api_client, "CancelTransaction", {"id": "pm-h", "reason": 5})["error"]["code"] == -31007


def test_expired_transaction(api_client, make_order):
    order = make_order()
    old = now_ms() - TIMEOUT_MS - 1000
    r = rpc(
        api_client,
        "CreateTransaction",
        {"id": "pm-old", "time": old, "amount": 302500000, "account": acc(order)},
    )
    assert r["error"]["code"] == -31008
    rpc(
        api_client,
        "CreateTransaction",
        {"id": "pm-new", "time": now_ms(), "amount": 302500000, "account": acc(order)},
    )
    Payment.objects.filter(provider_txn_id="pm-new").update(provider_time=old)
    assert rpc(api_client, "PerformTransaction", {"id": "pm-new"})["error"]["code"] == -31008
    assert Payment.objects.get(provider_txn_id="pm-new").cancel_reason == 4


def test_perform_on_cancelled_order_fails(api_client, make_order):
    from apps.orders.state import transition

    order = make_order()
    rpc(
        api_client,
        "CreateTransaction",
        {"id": "pm-k", "time": now_ms(), "amount": 302500000, "account": acc(order)},
    )
    transition(order, "cancelled", actor_type="staff")
    assert rpc(api_client, "PerformTransaction", {"id": "pm-k"})["error"]["code"] == -31008
    order.refresh_from_db()
    assert order.paid_amount == 0


def test_statement(api_client, make_order):
    order = make_order()
    t = now_ms()
    rpc(
        api_client, "CreateTransaction", {"id": "pm-s", "time": t, "amount": 302500000, "account": acc(order)}
    )
    r = rpc(api_client, "GetStatement", {"from": t - 1000, "to": t + 1000})
    assert [x["id"] for x in r["result"]["transactions"]] == ["pm-s"]
    assert r["result"]["transactions"][0]["account"] == acc(order)


def test_checkout_url(make_order):
    order = make_order()
    resp = order.client.post(reverse("order-pay", args=[order.number]), {"provider": "payme"}, format="json")
    assert resp.status_code == 200, resp.json()
    url = resp.json()["payment_url"]
    decoded = base64.b64decode(url.rsplit("/", 1)[1]).decode()
    assert decoded == f"m=m-123;ac.order_id={order.number};a=302500000"
    resp = order.client.post(reverse("order-pay", args=[order.number]), {"provider": "click"}, format="json")
    assert resp.json()["error"]["code"] == "provider_mismatch"
