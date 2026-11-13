import pytest
from django.urls import reverse

from apps.geo.models import Region

pytestmark = pytest.mark.django_db


def test_regions_seeded_and_listed(api_client):
    resp = api_client.get(reverse("geo-regions"))
    assert resp.status_code == 200
    assert len(resp.json()) == 14
    assert resp.json()[0]["name"] == "Toshkent shahri"


def test_regions_localized(api_client):
    resp = api_client.get(reverse("geo-regions"), HTTP_ACCEPT_LANGUAGE="ru")
    assert resp.json()[0]["name"] == "город Ташкент"
    resp = api_client.get(reverse("geo-regions"), HTTP_ACCEPT_LANGUAGE="uz-cyrl")
    assert resp.json()[0]["name"] == "Тошкент шаҳри"


def test_districts(api_client):
    tashkent = Region.objects.get(soato_code="1726")
    resp = api_client.get(reverse("geo-districts", args=[tashkent.id]))
    assert resp.status_code == 200
    assert len(resp.json()) == 12


def test_districts_unknown_region(api_client):
    resp = api_client.get(reverse("geo-districts", args=[999999]))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
