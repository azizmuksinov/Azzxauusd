import pytest
from django.urls import reverse

from apps.catalog.models import Product
from apps.catalog.tests import factories as f

pytestmark = pytest.mark.django_db


@pytest.fixture
def wh_client(staff_client):
    return staff_client("warehouse")


def test_receipt_with_imei_and_serial_search(wh_client, staff_client):
    v = f.product(f.category(), serial_tracking=Product.SerialTracking.IMEI).variants.first()
    wh = f.warehouse()
    imei = f.luhn_imei("35123400000001")
    resp = wh_client.post(
        reverse("admin-stock-receipt"),
        {
            "warehouse": wh.id,
            "variant": v.id,
            "qty": 1,
            "serials": [{"imei1": imei}],
            "document": "YX-77",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["on_hand"] == 1 and resp.json()["available"] == 1

    found = wh_client.get(reverse("admin-serials"), {"q": imei}).json()["results"]
    assert found[0]["imei1"] == imei and found[0]["history"][0]["ref"] == "receipt:YX-77"
    # support ham seriya raqam bo'yicha qidira oladi (kafolat arizalari uchun)
    assert staff_client("support").get(reverse("admin-serials"), {"q": imei}).status_code == 200

    resp = wh_client.post(
        reverse("admin-stock-receipt"),
        {
            "warehouse": wh.id,
            "variant": v.id,
            "qty": 1,
            "serials": [{"imei1": "123"}],
        },
        format="json",
    )
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "imei_invalid"


def test_stock_list_adjust_movements(wh_client):
    v = f.product(f.category()).variants.first()
    wh = f.warehouse()
    f.stock(v, 5, wh)
    resp = wh_client.post(
        reverse("admin-stock-adjustment"),
        {"warehouse": wh.id, "variant": v.id, "on_hand": 2, "comment": "inventarizatsiya"},
        format="json",
    )
    assert resp.status_code == 200 and resp.json()["on_hand"] == 2

    rows = wh_client.get(reverse("admin-stock"), {"low_stock": 3}).json()["results"]
    assert [r["sku"] for r in rows] == [v.sku]
    moves = wh_client.get(reverse("admin-stock-movements"), {"variant": v.id}).json()["results"]
    assert [m["reason"] for m in moves] == ["adjustment", "receipt"]


def test_inventory_permissions(staff_client, api_client):
    assert api_client.get(reverse("admin-stock")).status_code == 401
    assert staff_client("content_manager").get(reverse("admin-stock")).status_code == 403
    assert staff_client("content_manager").get(reverse("admin-serials")).status_code == 403
