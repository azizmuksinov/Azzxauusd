from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Address
from apps.catalog.tests import factories as f
from apps.geo.models import District
from apps.logistics.models import DeliveryTariff, DeliveryZone


@pytest.fixture
def tashkent_zone():
    zone = DeliveryZone.objects.create(name="Toshkent shahri", eta_days_min=1, eta_days_max=2)
    zone.regions.add(District.objects.filter(region__soato_code="1726").first().region)
    DeliveryTariff.objects.create(
        zone=zone, vehicle="standard", max_weight_kg=Decimal("5"), price=Decimal("25000")
    )
    DeliveryTariff.objects.create(zone=zone, vehicle="standard", max_weight_kg=None, price=Decimal("40000"))
    DeliveryTariff.objects.create(zone=zone, vehicle="truck", max_weight_kg=None, price=Decimal("120000"))
    return zone


@pytest.fixture
def address(user):
    return Address.objects.create(
        user=user,
        district=District.objects.filter(region__soato_code="1726").first(),
        street="Amir Temur",
        house="1",
        floor=5,
        elevator="none",
        recipient_name="Ali",
        recipient_phone="+998901112233",
    )


@pytest.fixture
def phone_variant():
    v = f.product(f.category(), price="3000000").variants.first()
    v.weight_kg = Decimal("0.5")
    v.save()
    f.stock(v, 5)
    return v


@pytest.fixture
def fridge_variant():
    v = f.product(f.category(), price="8000000", is_bulky=True).variants.first()
    v.weight_kg = Decimal("70")
    v.save()
    f.stock(v, 3)
    return v


@pytest.fixture
def client_with_cart(user):
    def make(*items):
        c = APIClient()
        c.force_authenticate(user)
        for variant, qty in items:
            assert (
                c.post(
                    reverse("cart-items"), {"variant_id": variant.id, "qty": qty}, format="json"
                ).status_code
                == 201
            )
        return c

    return make
