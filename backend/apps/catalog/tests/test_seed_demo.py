import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_seed_demo_idempotent_and_browsable(api_client, settings):
    settings.DEMO_MODE = True
    call_command("seed_demo")
    call_command("seed_demo")  # ikkinchi marta — xatosiz, dublikatsiz
    resp = api_client.get(reverse("product-list"), {"category": "maishiy-texnika", "f[inverter]": "true"})
    assert resp.status_code == 200
    assert {p["slug"] for p in resp.json()["results"]} == {"samsung-rb38", "lg-f2v5hs0w", "artel-12-inverter"}
    assert api_client.get(reverse("product-list")).json()["count"] == 14


def test_seed_demo_refuses_in_prod(settings):
    settings.DEMO_MODE = False
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_demo")


def test_seed_demo_delivery_works(user, settings):
    import uuid

    from rest_framework.test import APIClient

    from apps.accounts.models import Address
    from apps.catalog.models import ProductVariant
    from apps.geo.models import District

    settings.DEMO_MODE = True
    call_command("seed_demo")
    c = APIClient()
    c.force_authenticate(user)
    v = ProductVariant.objects.get(sku="DEMO-FR-AR455")
    c.post(reverse("cart-items"), {"variant_id": v.id, "qty": 1}, format="json")
    addr = Address.objects.create(
        user=user,
        district=District.objects.filter(region__soato_code="1726").first(),
        street="x",
        house="1",
        floor=4,
        recipient_name="a",
        recipient_phone=user.phone,
    )
    q = c.post(reverse("checkout-delivery"), {"address_id": addr.id}, format="json").json()
    assert "error" not in q, q
    assert q["delivery_price"] == "120000.00" and q["lifting"] == {"available": False, "price": None}
    resp = c.post(
        reverse("orders"),
        {"address_id": addr.id, "quote_id": q["quote_id"], "payment_method": "cash"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    # yetkazish narxi oldindan onlayn, tovar narxi eshikda
    assert (data["total"], data["required_prepayment"], data["cod_amount"]) == (
        "5610000.00",
        "120000.00",
        "5490000.00",
    )


def test_seed_demo_creates_demo_staff(settings):
    from apps.accounts.models import User
    from apps.delivery.models import Courier

    settings.DEMO_MODE = True
    call_command("seed_demo")
    courier = Courier.objects.get(user__phone="+998900000001")
    assert courier.vehicle == "truck" and courier.user.groups.filter(name="courier").exists()
    staff = User.objects.get(phone="+998900000002")
    roles = set(staff.groups.values_list("name", flat=True))
    assert roles == {"warehouse", "logistics_manager", "finance", "support"}
