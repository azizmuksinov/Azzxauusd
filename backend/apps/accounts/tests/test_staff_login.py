import pytest
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts import staff_auth
from apps.accounts.models import User
from apps.accounts.otp import request_otp

pytestmark = pytest.mark.django_db
PASSWORD = "Juda-Maxfiy-2026"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def make_staff(login="ali", role="warehouse", password=PASSWORD):
    user = User.objects.create_user("+998901230001", first_name="Ali")
    user.groups.add(Group.objects.get(name=role))
    staff_auth.set_credentials(user, login=login, password=password)
    return user


def sign_in(login, password):
    return APIClient().post(reverse("staff-login"), {"login": login, "password": password}, format="json")


def test_staff_signs_in_with_login_and_password():
    user = make_staff()
    r = sign_in(" ALI ", PASSWORD)  # login katta-kichik harf va bo'shliqqa bog'liq emas
    assert r.status_code == 200, r.json()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    me = client.get(reverse("me")).json()
    assert me["id"] == user.id and me["login"] == "ali" and me["roles"] == ["warehouse"]


def test_wrong_password_unknown_login_and_customer_are_refused():
    make_staff()
    assert sign_in("ali", "xato-parol-1").json()["error"]["code"] == "bad_credentials"
    assert sign_in("yoq", PASSWORD).json()["error"]["code"] == "bad_credentials"
    # Roli yo'q foydalanuvchi (xaridor) parol bilan ham kira olmaydi.
    customer = User.objects.create_user("+998901230002", password=PASSWORD)
    customer.login = "xaridor"
    customer.save()
    assert sign_in("xaridor", PASSWORD).status_code == 401
    # Bloklangan xodim.
    User.objects.filter(login="ali").update(is_active=False)
    assert sign_in("ali", PASSWORD).status_code == 401


def test_login_is_locked_after_repeated_failures():
    make_staff()
    for _ in range(staff_auth.MAX_FAILS):
        assert sign_in("ali", "xato-parol-1").status_code == 401
    r = sign_in("ali", PASSWORD)  # to'g'ri parol ham vaqtincha qabul qilinmaydi
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


def test_staff_cannot_sign_in_with_sms_code(settings):
    settings.DEMO_MODE = True
    user = make_staff()
    code = request_otp(user.phone, None).debug_code
    r = APIClient().post(reverse("otp-verify"), {"phone": user.phone, "code": code}, format="json")
    assert r.status_code == 403 and r.json()["error"]["code"] == "staff_password_required"


def test_only_admin_issues_and_changes_credentials(staff_client):
    admin = staff_client("admin")
    url = reverse("admin-staff-list")
    body = {"phone": "90 111 22 33", "first_name": "Vali", "roles": ["finance"]}
    # login va parolsiz xodim qo'shilmaydi
    assert admin.post(url, body, format="json").status_code == 400
    assert not User.objects.filter(phone="+998901112233").exists()
    weak = admin.post(url, {**body, "login": "vali", "password": "12345"}, format="json")
    assert weak.json()["error"]["code"] == "password_weak"
    r = admin.post(url, {**body, "login": "Vali", "password": PASSWORD}, format="json")
    assert r.status_code == 201, r.json()
    assert r.json()["login"] == "vali" and r.json()["has_password"] is True and "password" not in r.json()
    uid = r.json()["id"]
    old_refresh = sign_in("vali", PASSWORD).json()["refresh"]

    # band login
    clash = admin.post(
        url,
        {"phone": "901112244", "roles": ["support"], "login": "vali", "password": PASSWORD},
        format="json",
    )
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "login_taken"

    # admin parolni almashtiradi: eski parol va eski seans ishlamaydi
    detail = reverse("admin-staff-detail", args=[uid])
    assert admin.patch(detail, {"password": "Yangi-Parol-2026"}, format="json").status_code == 200
    assert sign_in("vali", PASSWORD).status_code == 401
    assert sign_in("vali", "Yangi-Parol-2026").status_code == 200
    refresh = APIClient().post(reverse("token-refresh"), {"refresh": old_refresh}, format="json")
    assert refresh.status_code == 401

    # bloklash
    assert admin.patch(detail, {"is_active": False}, format="json").json()["is_active"] is False
    assert sign_in("vali", "Yangi-Parol-2026").status_code == 401
    # admin bo'lmagan xodim parol bera olmaydi
    other = staff_client("finance")
    assert other.patch(detail, {"password": "Boshqa-Parol-2026"}, format="json").status_code == 403


def test_admin_from_environment_closes_demo_accounts(monkeypatch, settings):
    demo = make_staff(login="admin", role="admin", password=settings.DEMO_STAFF_PASSWORD)
    settings.DEMO_MODE = True
    assert [a["login"] for a in staff_auth.demo_accounts()] == ["admin"]

    monkeypatch.setenv("ADMIN_LOGIN", "boshliq")
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("ADMIN_PHONE", "+998901239999")
    call_command("ensure_staff_admin")
    assert sign_in("boshliq", PASSWORD).status_code == 200
    assert User.objects.get(login="boshliq").has_role("admin")
    demo.refresh_from_db()
    assert (
        not demo.has_usable_password() and sign_in("admin", settings.DEMO_STAFF_PASSWORD).status_code == 401
    )
    assert staff_auth.demo_accounts() == []
    # parolni muhit o'zgaruvchisi orqali almashtirish
    monkeypatch.setenv("ADMIN_PASSWORD", "Almashgan-Parol-2026")
    call_command("ensure_staff_admin")
    assert sign_in("boshliq", "Almashgan-Parol-2026").status_code == 200
