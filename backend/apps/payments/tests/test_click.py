import hashlib

import pytest
from django.urls import reverse

from apps.payments.models import Payment

pytestmark = pytest.mark.django_db

SECRET = "click-secret"


def signed(data: dict, complete=False) -> dict:
    prep = data.get("merchant_prepare_id", "") if complete else ""
    raw = (
        f"{data['click_trans_id']}{data['service_id']}{SECRET}{data['merchant_trans_id']}{prep}"
        f"{data['amount']}{data['action']}{data['sign_time']}"
    )
    return {**data, "sign_string": hashlib.md5(raw.encode()).hexdigest()}  # noqa: S324


def base(order, amount="3025000.00", action=0, trans="c-1"):
    return {
        "click_trans_id": trans,
        "service_id": "777",
        "click_paydoc_id": "pd-1",
        "merchant_trans_id": order.number,
        "amount": amount,
        "action": action,
        "error": 0,
        "error_note": "Success",
        "sign_time": "2026-11-07 12:00:00",
    }


def prepare(api_client, data):
    return api_client.post(reverse("webhook-click-prepare"), data).json()  # form-encoded


def complete(api_client, data):
    return api_client.post(reverse("webhook-click-complete"), data).json()


def test_full_flow(api_client, make_order):
    order = make_order("click")
    r = prepare(api_client, signed(base(order)))
    assert r["error"] == 0, r
    prep_id = r["merchant_prepare_id"]
    r = complete(api_client, signed({**base(order, action=1), "merchant_prepare_id": prep_id}, complete=True))
    assert r["error"] == 0 and r["merchant_confirm_id"] == prep_id
    order.refresh_from_db()
    assert order.status == "paid" and order.paid_amount == 3025000
    # takroriy complete
    r = complete(api_client, signed({**base(order, action=1), "merchant_prepare_id": prep_id}, complete=True))
    assert r["error"] == -4


def test_bad_signature(api_client, make_order):
    order = make_order("click")
    data = signed(base(order))
    data["amount"] = "1.00"  # imzodan keyin o'zgartirildi
    assert prepare(api_client, data)["error"] == -1
    assert not Payment.objects.exists()


def test_wrong_amount_and_unknown_order(api_client, make_order):
    order = make_order("click")
    assert prepare(api_client, signed(base(order, amount="100.00")))["error"] == -2
    other = base(order)
    other["merchant_trans_id"] = "nope"
    assert prepare(api_client, signed(other))["error"] == -5


def test_click_side_error_cancels(api_client, make_order):
    order = make_order("click")
    prep_id = prepare(api_client, signed(base(order)))["merchant_prepare_id"]
    data = {**base(order, action=1), "merchant_prepare_id": prep_id, "error": -5017}
    assert complete(api_client, signed(data, complete=True))["error"] == -9
    assert Payment.objects.get().status == "cancelled"
    order.refresh_from_db()
    assert order.status == "created"


def test_complete_unknown_prepare(api_client, make_order):
    order = make_order("click")
    data = {**base(order, action=1), "merchant_prepare_id": 999}
    assert complete(api_client, signed(data, complete=True))["error"] == -6


def test_missing_fields(api_client):
    assert prepare(api_client, {"click_trans_id": "1"})["error"] == -8


def test_checkout_url(make_order):
    order = make_order("click")
    url = order.client.post(
        reverse("order-pay", args=[order.number]), {"provider": "click"}, format="json"
    ).json()["payment_url"]
    assert (
        "service_id=777" in url and f"transaction_param={order.number}" in url and "amount=3025000.00" in url
    )
