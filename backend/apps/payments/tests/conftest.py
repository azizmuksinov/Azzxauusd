import uuid

import pytest
from django.urls import reverse

from apps.orders.models import Order
from apps.orders.tests.conftest import address, client_with_cart, fridge_variant, phone_variant, tashkent_zone  # noqa: F401


@pytest.fixture(autouse=True)
def provider_keys(settings):
    settings.PAYME = {**settings.PAYME, "MERCHANT_ID": "m-123", "KEY": "payme-test-key"}
    settings.CLICK = {
        **settings.CLICK,
        "SERVICE_ID": "777",
        "MERCHANT_ID": "555",
        "SECRET_KEY": "click-secret",
    }
    settings.UZUM = {**settings.UZUM, "SERVICE_ID": "4242", "LOGIN": "uzum", "PASSWORD": "uzum-pass"}


@pytest.fixture
def make_order(client_with_cart, phone_variant, address, tashkent_zone):  # noqa: F811
    """make_order("payme") -> Order (telefon 3 000 000 + yetkazish 25 000)."""

    def make(method="payme", qty=1):
        c = client_with_cart((phone_variant, qty))
        qid = c.post(reverse("checkout-delivery"), {"address_id": address.id}, format="json").json()[
            "quote_id"
        ]
        resp = c.post(
            reverse("orders"),
            {"address_id": address.id, "quote_id": qid, "payment_method": method},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert resp.status_code == 201, resp.json()
        order = Order.objects.get(number=resp.json()["number"])
        order.client = c
        return order

    return make
