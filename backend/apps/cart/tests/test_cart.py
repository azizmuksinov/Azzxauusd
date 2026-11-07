import uuid

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.cart.models import Cart
from apps.catalog.tests import factories as f
from apps.core.settings_registry import set_setting

pytestmark = pytest.mark.django_db


@pytest.fixture
def variant():
    v = f.product(f.category(), price="1000000").variants.first()
    f.stock(v, 5)
    return v


def add(client, variant_id, qty=1, token=None):
    headers = {"HTTP_X_CART_TOKEN": token} if token else {}
    return client.post(
        reverse("cart-items"), {"variant_id": variant_id, "qty": qty}, format="json", **headers
    )


def test_guest_cart_flow(api_client, variant):
    resp = add(api_client, variant.id, 2)
    assert resp.status_code == 201, resp.json()
    token = resp.json()["guest_token"]
    assert resp["X-Cart-Token"] == token
    data = add(api_client, variant.id, 1, token).json()
    assert data["items"][0]["qty"] == 3 and data["subtotal"] == "3000000.00" and data["can_checkout"]

    item_id = data["items"][0]["id"]
    resp = api_client.patch(
        reverse("cart-item", args=[item_id]), {"qty": 1}, format="json", HTTP_X_CART_TOKEN=token
    )
    assert resp.json()["subtotal"] == "1000000.00"
    resp = api_client.delete(reverse("cart-item", args=[item_id]), HTTP_X_CART_TOKEN=token)
    assert resp.json()["items"] == []


def test_other_guest_cannot_touch_item(api_client, variant):
    data = add(api_client, variant.id).json()
    item_id = data["items"][0]["id"]
    other = str(uuid.uuid4())
    assert api_client.delete(reverse("cart-item", args=[item_id]), HTTP_X_CART_TOKEN=other).status_code == 404


def test_stock_and_qty_limits(api_client, variant):
    resp = add(api_client, variant.id, 6)
    assert resp.status_code == 409 and resp.json()["error"] == {
        "code": "not_enough_stock",
        "message": "Omborda shuncha tovar yo'q.",
        "available": 5,
    }
    set_setting("cart_max_qty_per_item", 2)
    resp = add(api_client, variant.id, 3)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "qty_limit"


def test_unavailable_variant(api_client, variant):
    variant.product.status = "draft"
    variant.product.save()
    assert add(api_client, variant.id).status_code == 404


def test_problem_lines_block_checkout(auth_client, variant):
    add(auth_client, variant.id, 2)
    variant.stocks.update(on_hand=1)
    data = auth_client.get(reverse("cart")).json()
    assert data["items"][0]["problem"] == "not_enough_stock" and data["can_checkout"] is False
    variant.is_active = False
    variant.save()
    data = auth_client.get(reverse("cart")).json()
    assert data["items"][0]["problem"] == "unavailable" and data["subtotal"] == "0"


def test_user_cart_has_no_guest_token(auth_client, variant):
    data = add(auth_client, variant.id).json()
    assert data["guest_token"] is None


def test_merge_guest_into_user(user, variant):
    other = f.product(f.category()).variants.first()
    f.stock(other, 10)
    guest = APIClient()
    token = add(guest, variant.id, 2).json()["guest_token"]
    add(guest, other.id, 1, token)

    client = APIClient()
    client.force_authenticate(user)
    add(client, variant.id, 2)
    resp = client.post(reverse("cart-merge"), {"guest_token": token}, format="json")
    assert resp.status_code == 200
    qty = {i["variant_id"]: i["qty"] for i in resp.json()["items"]}
    assert qty == {variant.id: 4, other.id: 1}
    assert not Cart.objects.filter(guest_token=token).exists()


def test_merge_respects_stock(user, variant):
    guest = APIClient()
    token = add(guest, variant.id, 4).json()["guest_token"]
    client = APIClient()
    client.force_authenticate(user)
    add(client, variant.id, 3)
    qty = client.post(reverse("cart-merge"), {"guest_token": token}, format="json").json()["items"][0]["qty"]
    assert qty == 5  # 3 + 4, lekin omborda 5 ta


def test_invalid_token_header(api_client):
    assert (
        api_client.get(reverse("cart"), HTTP_X_CART_TOKEN="xyz").json()["error"]["code"]
        == "invalid_cart_token"
    )
