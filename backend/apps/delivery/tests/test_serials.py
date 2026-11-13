import pytest
from django.urls import reverse

from apps.catalog.tests import factories as f
from apps.inventory.models import SerialUnit
from apps.inventory.services import SerialInput, receive

pytestmark = pytest.mark.django_db

INSPECTION = {"packaging_intact": True, "appearance_ok": True, "complete_set": True}


@pytest.fixture
def imei_variant(phone_variant):
    p = phone_variant.product
    p.serial_tracking = "imei"
    p.save()
    imeis = [f.luhn_imei(f"3520990000000{i}") for i in range(3)]
    receive(f.warehouse(), phone_variant, 3, serials=[SerialInput(imei1=x) for x in imeis])
    return phone_variant


def test_pack_requires_imei_and_follows_order(make_order, imei_variant, staff, issued_route, courier_client):
    order = make_order(variant=imei_variant)
    staff.post(reverse("admin-order-start-picking", args=[order.number]))
    item = order.items.get()
    r = staff.post(reverse("admin-order-pack", args=[order.number]), {}, format="json")
    assert r.status_code == 400 and r.json()["error"]["code"] == "serials_count_mismatch"

    unit = SerialUnit.objects.filter(variant=imei_variant, status="in_stock").first()
    r = staff.post(
        reverse("admin-order-pack", args=[order.number]),
        {"serials": {str(item.id): [unit.id]}},
        format="json",
    )
    assert r.status_code == 200, r.json()
    assert r.json()["items"][0]["serials"][0]["imei1"] == unit.imei1
    unit.refresh_from_db()
    assert unit.status == "reserved"

    order.refresh_from_db()
    route = issued_route(order)
    unit.refresh_from_db()
    assert unit.status == "sold" and unit.warehouse_id is None

    sid = route["stops"][0]["id"]
    courier_client.post(reverse("courier-stop-start", args=[sid]))
    r = courier_client.post(reverse("courier-stop-refuse", args=[sid]), {"reason": "Nuqson"}, format="json")
    assert r.status_code == 200
    staff.post(reverse("admin-route-sheet-close", args=[route["id"]]))
    unit.refresh_from_db()
    assert unit.status == "in_stock" and unit.warehouse_id == f.warehouse().id


def test_serial_already_used(make_order, imei_variant, staff):
    o1, o2 = make_order(variant=imei_variant), make_order(variant=imei_variant)
    unit = SerialUnit.objects.filter(variant=imei_variant).first()
    for o in (o1, o2):
        staff.post(reverse("admin-order-start-picking", args=[o.number]))
    body = lambda o: {"serials": {str(o.items.get().id): [unit.id]}}  # noqa: E731
    assert (
        staff.post(reverse("admin-order-pack", args=[o1.number]), body(o1), format="json").status_code == 200
    )
    r = staff.post(reverse("admin-order-pack", args=[o2.number]), body(o2), format="json")
    assert r.json()["error"]["code"] == "serial_unavailable"


def test_cancel_after_pack_frees_serial(make_order, imei_variant, staff):
    from apps.orders.state import transition

    order = make_order(variant=imei_variant)
    staff.post(reverse("admin-order-start-picking", args=[order.number]))
    unit = SerialUnit.objects.filter(variant=imei_variant).first()
    staff.post(
        reverse("admin-order-pack", args=[order.number]),
        {"serials": {str(order.items.get().id): [unit.id]}},
        format="json",
    )
    order.refresh_from_db()
    transition(order, "cancelled", actor_type="staff")
    unit.refresh_from_db()
    assert unit.status == "in_stock"
