import pytest
from django.urls import reverse

from apps.geo.models import Region

pytestmark = pytest.mark.django_db


def test_zone_and_tariff_crud(staff_client):
    c = staff_client("logistics_manager")
    region = Region.objects.get(soato_code="1727")
    resp = c.post(
        reverse("admin-delivery-zone-list"),
        {"name": "Toshkent viloyati", "regions": [region.id], "eta_days_min": 1, "eta_days_max": 3},
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    zone_id = resp.json()["id"]
    resp = c.post(
        reverse("admin-delivery-tariff-list"),
        {"zone": zone_id, "vehicle": "truck", "price": "150000"},
        format="json",
    )
    assert resp.status_code == 201
    zone = c.get(reverse("admin-delivery-zone-detail", args=[zone_id])).json()
    assert zone["tariffs"][0]["price"] == "150000.00"
    resp = c.post(
        reverse("admin-delivery-zone-list"),
        {"name": "x", "eta_days_min": 5, "eta_days_max": 2},
        format="json",
    )
    assert resp.status_code == 400
    assert staff_client("content_manager").get(reverse("admin-delivery-zone-list")).status_code == 403


def test_district_zone_overrides_region(staff_client):
    from decimal import Decimal

    from apps.geo.models import District
    from apps.logistics.models import DeliveryTariff, DeliveryZone
    from apps.logistics.providers.manual import find_zone

    district = District.objects.filter(region__soato_code="1726").first()
    region_zone = DeliveryZone.objects.create(name="Shahar")
    region_zone.regions.add(district.region)
    special = DeliveryZone.objects.create(name="Uzoq tuman")
    special.districts.add(district)
    DeliveryTariff.objects.create(zone=special, price=Decimal("1"))
    assert find_zone(district.region_id, district.id) == special
    other = District.objects.filter(region=district.region).exclude(pk=district.pk).first()
    assert find_zone(district.region_id, other.id) == region_zone
