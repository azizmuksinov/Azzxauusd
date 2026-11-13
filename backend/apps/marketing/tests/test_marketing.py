from decimal import Decimal

import pytest
from django.urls import reverse

from apps.catalog.models import PriceHistory
from apps.catalog.tests import factories as f

pytestmark = pytest.mark.django_db


def test_banners(staff_client, api_client):
    c = staff_client("content_manager")
    r = c.post(
        reverse("admin-banner-list"),
        {"title": {"uz": "Aksiya", "ru": "Акция"}, "link": "/c/tv", "color": "#111111"},
        format="json",
    )
    assert r.status_code == 201, r.json()
    c.post(reverse("admin-banner-list"), {"title": {"uz": "Yashirin"}, "is_active": False}, format="json")
    data = api_client.get(reverse("banners")).json()
    assert [b["title"] for b in data] == ["Aksiya"]
    assert api_client.get(reverse("banners"), HTTP_ACCEPT_LANGUAGE="ru").json()[0]["title"] == "Акция"
    assert (
        c.post(
            reverse("admin-banner-list"), {"title": {"uz": "x"}, "color": "red"}, format="json"
        ).status_code
        == 400
    )
    assert staff_client("warehouse").get(reverse("admin-banner-list")).status_code == 403


def test_bulk_discount(staff_client):
    root = f.category()
    leaf = f.category(parent=root)
    p1 = f.product(leaf, price="1000000")
    p2 = f.product(f.category(), price="500000")
    c = staff_client("content_manager")
    url = reverse("admin-bulk-discount")
    r = c.post(url, {"action": "apply", "percent": 15, "category": root.id}, format="json")
    assert r.json() == {"variants": 1}
    v = p1.variants.get()
    assert v.price == Decimal("850000") and v.old_price == Decimal("1000000")
    # takroriy chegirma asl narxdan hisoblanadi (ustma-ust emas)
    c.post(url, {"action": "apply", "percent": 20, "category": root.id}, format="json")
    v.refresh_from_db()
    assert v.price == Decimal("800000") and v.old_price == Decimal("1000000")
    assert PriceHistory.objects.filter(variant=v).count() == 2
    assert p2.variants.get().old_price is None

    assert c.post(url, {"action": "remove", "category": root.id}, format="json").json() == {"variants": 1}
    v.refresh_from_db()
    assert v.price == Decimal("1000000") and v.old_price is None
    assert (
        c.post(url, {"action": "apply", "percent": 10}, format="json").json()["error"]["code"]
        == "scope_required"
    )
