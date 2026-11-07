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
