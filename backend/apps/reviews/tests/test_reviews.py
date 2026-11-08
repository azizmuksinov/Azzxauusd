import pytest
from django.urls import reverse

from apps.catalog.tests import factories as f
from apps.orders.models import Order, OrderItem

pytestmark = pytest.mark.django_db


@pytest.fixture
def product():
    return f.product(f.category(), slug="tv-1")


def deliver(user, product, status="delivered"):
    o = Order.objects.create(
        user=user,
        payment_method="cash",
        subtotal=1,
        delivery_fee=0,
        total=1,
        address_snapshot={},
        recipient_name="A",
        recipient_phone="+998901112233",
        delivery_provider="own",
        delivery_vehicle="standard",
        delivery_eta_min=1,
        delivery_eta_max=2,
        idempotency_key=f"k-{product.pk}-{status}",
        status=status,
    )
    v = product.variants.first()
    OrderItem.objects.create(
        order=o,
        variant=v,
        product_name={"uz": "x"},
        sku=v.sku,
        qty=1,
        unit_price=1,
        line_total=1,
        warranty_months=12,
        vat_percent=12,
    )


def test_only_buyers_can_review(auth_client, user, product, api_client):
    url = reverse("product-reviews", args=[product.slug])
    assert auth_client.get(url).json()["can_review"] is False
    r = auth_client.post(url, {"rating": 5, "text": "Zo'r"}, format="json")
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_purchased"

    deliver(user, product, status="in_transit")  # hali yetkazilmagan
    assert auth_client.get(url).json()["can_review"] is False
    deliver(user, product)
    assert auth_client.get(url).json()["can_review"] is True

    r = auth_client.post(url, {"rating": 4, "text": "Yaxshi", "pros": "Tez", "cons": ""}, format="json")
    assert r.status_code == 201, r.json()
    assert auth_client.post(url, {"rating": 1}, format="json").json()["error"]["code"] == "already_reviewed"
    assert auth_client.post(url, {"rating": 6}, format="json").status_code in (400, 409)

    data = api_client.get(url).json()
    assert data["rating_count"] == 1 and data["rating_avg"] == "4.00"
    assert data["distribution"]["4"] == 1 and data["results"][0]["author"] == "Ali"
    product.refresh_from_db()
    assert product.rating_count == 1


def test_moderation(auth_client, user, product, staff_client, api_client):
    deliver(user, product)
    auth_client.post(
        reverse("product-reviews", args=[product.slug]), {"rating": 1, "text": "yomon"}, format="json"
    )
    support = staff_client("support")
    rid = support.get(reverse("admin-review-list")).json()["results"][0]["id"]
    r = support.patch(
        reverse("admin-review-detail", args=[rid]), {"is_published": False, "reply": "Uzr"}, format="json"
    )
    assert r.status_code == 200
    data = api_client.get(reverse("product-reviews", args=[product.slug])).json()
    assert data["rating_count"] == 0 and data["results"] == []
    assert staff_client("warehouse").get(reverse("admin-review-list")).status_code == 403
