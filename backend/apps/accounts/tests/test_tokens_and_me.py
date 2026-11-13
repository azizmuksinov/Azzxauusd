import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

pytestmark = pytest.mark.django_db


def bearer(token) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_me_requires_auth(api_client):
    resp = api_client.get(reverse("me"))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "not_authenticated"


def test_me_get_and_patch(user):
    client = bearer(RefreshToken.for_user(user).access_token)
    resp = client.get(reverse("me"))
    assert resp.json()["phone"] == "+998901112233"
    resp = client.patch(
        reverse("me"), {"last_name": "Valiyev", "language": "ru", "phone": "+998999999999"}, format="json"
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.last_name == "Valiyev" and user.language == "ru"
    assert user.phone == "+998901112233"  # telefon PATCH orqali o'zgarmaydi


def test_me_roles(user):
    from django.contrib.auth.models import Group

    user.groups.add(Group.objects.get(name="courier"))
    resp = bearer(RefreshToken.for_user(user).access_token).get(reverse("me"))
    assert resp.json()["roles"] == ["courier"]


def test_refresh_rotation(user):
    refresh = RefreshToken.for_user(user)
    resp = APIClient().post(reverse("token-refresh"), {"refresh": str(refresh)}, format="json")
    assert resp.status_code == 200
    assert resp.json()["access"] and resp.json()["refresh"] != str(refresh)

    # rotation'dan keyin eski refresh token qayta ishlamaydi
    resp = APIClient().post(reverse("token-refresh"), {"refresh": str(refresh)}, format="json")
    assert resp.status_code == 401


def test_logout_blacklists(user):
    refresh = RefreshToken.for_user(user)
    client = bearer(refresh.access_token)
    assert client.post(reverse("logout"), {"refresh": str(refresh)}, format="json").status_code == 204
    resp = APIClient().post(reverse("token-refresh"), {"refresh": str(refresh)}, format="json")
    assert resp.status_code == 401


def test_logout_foreign_token_rejected(user, django_user_model):
    other = django_user_model.objects.create_user(phone="+998935556677")
    client = bearer(RefreshToken.for_user(user).access_token)
    resp = client.post(reverse("logout"), {"refresh": str(RefreshToken.for_user(other))}, format="json")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "token_invalid"


def test_delete_account_anonymizes(user):
    client = bearer(RefreshToken.for_user(user).access_token)
    assert client.delete(reverse("me")).status_code == 204
    user.refresh_from_db()
    assert user.phone == f"deleted-{user.pk}"
    assert not user.is_active and user.first_name == "" and user.deleted_at


def test_superuser_with_password(django_user_model):
    admin = django_user_model.objects.create_superuser("901234500", "a-strong-password")
    assert admin.phone == "+998901234500" and admin.is_staff and admin.check_password("a-strong-password")
