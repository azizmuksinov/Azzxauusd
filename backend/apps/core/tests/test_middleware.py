import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db


def test_default_denies_framing(client):
    resp = client.get("/health")
    assert resp["X-Frame-Options"] == "DENY"


@override_settings(
    MIDDLEWARE=["apps.core.middleware.FrameAncestorsMiddleware", "django.middleware.common.CommonMiddleware"],
    FRAME_ANCESTORS=["https://huggingface.co"],
)
def test_frame_ancestors_header(client):
    resp = client.get("/health")
    assert resp["Content-Security-Policy"] == "frame-ancestors 'self' https://huggingface.co"
    assert "X-Frame-Options" not in resp
