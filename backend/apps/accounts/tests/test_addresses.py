import pytest
from django.urls import reverse

from apps.accounts.models import Address
from apps.geo.models import District

pytestmark = pytest.mark.django_db


@pytest.fixture
def district():
    return District.objects.filter(region__soato_code="1726").first()


def payload(district, **extra):
    data = {
        "label": "Uy",
        "district": district.id,
        "street": "Amir Temur ko'chasi",
        "house": "12",
        "apartment": "45",
        "floor": 7,
        "elevator": "passenger",
        "landmark": "Metro yonida",
        "latitude": "41.311081",
        "longitude": "69.240562",
        "recipient_name": "Ali Valiyev",
        "recipient_phone": "93 123 45 67",
    }
    data.update(extra)
    return data


def test_first_address_becomes_default(auth_client, district):
    resp = auth_client.post(reverse("address-list"), payload(district), format="json")
    assert resp.status_code == 201, resp.json()
    assert resp.json()["is_default"] is True
    assert resp.json()["recipient_phone"] == "+998931234567"


def test_only_one_default(auth_client, district, user):
    auth_client.post(reverse("address-list"), payload(district), format="json")
    resp = auth_client.post(
        reverse("address-list"), payload(district, label="Ish", is_default=True), format="json"
    )
    assert resp.status_code == 201
    assert list(Address.objects.filter(user=user, is_default=True).values_list("label", flat=True)) == ["Ish"]


def test_delete_default_promotes_another(auth_client, district, user):
    a = auth_client.post(reverse("address-list"), payload(district), format="json").json()
    auth_client.post(reverse("address-list"), payload(district, label="Ish"), format="json")
    assert auth_client.delete(reverse("address-detail", args=[a["id"]])).status_code == 204
    assert Address.objects.get(user=user).is_default is True


def test_coordinates_validation(auth_client, district):
    resp = auth_client.post(
        reverse("address-list"), payload(district, latitude="55.75", longitude="37.61"), format="json"
    )
    assert resp.status_code == 400
    resp = auth_client.post(reverse("address-list"), payload(district, longitude=None), format="json")
    assert resp.status_code == 400


def test_cannot_access_foreign_address(auth_client, district, django_user_model):
    other = django_user_model.objects.create_user(phone="+998935556677")
    addr = Address.objects.create(
        user=other,
        district=district,
        street="X",
        house="1",
        recipient_name="B",
        recipient_phone="+998935556677",
    )
    assert auth_client.get(reverse("address-detail", args=[addr.id])).status_code == 404
    assert auth_client.delete(reverse("address-detail", args=[addr.id])).status_code == 404


def test_inactive_district_rejected(auth_client, district):
    district.is_active = False
    district.save()
    resp = auth_client.post(reverse("address-list"), payload(district), format="json")
    assert resp.status_code == 400
