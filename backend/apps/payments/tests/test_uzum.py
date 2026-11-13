import base64

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

AUTH = "Basic " + base64.b64encode(b"uzum:uzum-pass").decode()


def call(api_client, op, body, auth=AUTH):
    return api_client.post(
        reverse("webhook-uzum", args=[op]),
        {"serviceId": 4242, "timestamp": 1, **body},
        format="json",
        HTTP_AUTHORIZATION=auth,
    )


def test_auth(api_client, make_order):
    order = make_order("uzum")
    resp = call(api_client, "check", {"params": {"orderId": order.number}}, auth="Basic eDp5")
    assert resp.status_code == 401 and resp.json()["errorCode"] == "10001"


def test_full_flow(api_client, make_order):
    order = make_order("uzum")
    r = call(api_client, "check", {"params": {"orderId": order.number}}).json()
    assert r["status"] == "OK" and r["data"]["amount"]["value"] == 302500000
    r = call(
        api_client, "create", {"transId": "u-1", "params": {"orderId": order.number}, "amount": 302500000}
    ).json()
    assert r["status"] == "CREATED"
    r = call(api_client, "confirm", {"transId": "u-1"}).json()
    assert r["status"] == "CONFIRMED"
    order.refresh_from_db()
    assert order.status == "paid"
    assert call(api_client, "status", {"transId": "u-1"}).json()["status"] == "CONFIRMED"
    r = call(api_client, "reverse", {"transId": "u-1"}).json()
    assert r["status"] == "REVERSED"
    order.refresh_from_db()
    assert order.status == "cancelled" and order.paid_amount == 0


def test_errors(api_client, make_order):
    order = make_order("uzum")
    assert call(api_client, "check", {"params": {"orderId": "nope"}}).json()["errorCode"] == "10007"
    r = call(api_client, "create", {"transId": "u-2", "params": {"orderId": order.number}, "amount": 1})
    assert r.status_code == 400 and r.json()["errorCode"] == "10009"
    assert call(api_client, "confirm", {"transId": "none"}).json()["errorCode"] == "10014"
    assert call(api_client, "unknown", {}).json()["errorCode"] == "10003"
    resp = api_client.post(
        reverse("webhook-uzum", args=["check"]), {"serviceId": 1}, format="json", HTTP_AUTHORIZATION=AUTH
    )
    assert resp.json()["errorCode"] == "10006"


def test_payment_url_not_configured(make_order):
    order = make_order("uzum")
    resp = order.client.post(reverse("order-pay", args=[order.number]), {"provider": "uzum"}, format="json")
    assert resp.json()["error"]["code"] == "provider_url_unavailable"
