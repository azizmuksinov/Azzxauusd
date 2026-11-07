from decimal import Decimal

import pytest
from django.urls import reverse

from apps.core.settings_registry import get_setting, set_setting

pytestmark = pytest.mark.django_db


def test_defaults_and_override():
    assert get_setting("cod_max_amount") is None
    assert get_setting("cart_max_qty_per_item") == 10
    set_setting("cod_max_amount", "15000000")
    assert get_setting("cod_max_amount") == Decimal("15000000")
    set_setting("cod_max_amount", None)
    assert get_setting("cod_max_amount") is None


def test_non_nullable_rejects_none():
    with pytest.raises(ValueError):
        set_setting("cart_max_qty_per_item", None)


def test_admin_api(staff_client):
    admin = staff_client("admin")
    resp = admin.patch(
        reverse("admin-settings"),
        {"cod_max_amount": 20000000, "lifting_price_per_floor": "15000"},
        format="json",
    )
    assert resp.status_code == 200, resp.json()
    values = {s["key"]: s["value"] for s in resp.json()}
    assert values["cod_max_amount"] == "20000000" and values["lifting_price_per_floor"] == "15000"

    resp = admin.patch(reverse("admin-settings"), {"cart_max_qty_per_item": "ko'p"}, format="json")
    assert resp.status_code == 400 and "cart_max_qty_per_item" in resp.json()["error"]["fields"]
    assert (
        admin.patch(reverse("admin-settings"), {"nope": 1}, format="json").json()["error"]["code"]
        == "unknown_setting"
    )
    assert staff_client("content_manager").get(reverse("admin-settings")).status_code == 403
