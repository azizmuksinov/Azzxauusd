import pytest
from django.urls import reverse

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_admin_manages_staff_roles(staff_client):
    admin = staff_client("admin")
    url = reverse("admin-staff-list")
    r = admin.post(
        url,
        {
            "phone": "90 111 22 33",
            "first_name": "Ali",
            "roles": ["content_manager", "finance"],
            "login": "ali",
            "password": "Juda-Maxfiy-2026",
        },
        format="json",
    )
    assert r.status_code == 201, r.json()
    assert r.json()["phone"] == "+998901112233" and r.json()["roles"] == ["content_manager", "finance"]
    uid = r.json()["id"]
    assert any(x["id"] == uid for x in admin.get(url).json()["results"])
    assert admin.get(url, {"q": "1112233"}).json()["results"][0]["id"] == uid

    r = admin.patch(reverse("admin-staff-detail", args=[uid]), {"roles": ["warehouse"]}, format="json")
    assert r.json()["roles"] == ["warehouse"]
    assert admin.post(url, {"phone": "901112233", "roles": ["courier"]}, format="json").status_code == 400
    # o'zidan admin rolini olib bo'lmaydi
    me = User.objects.filter(groups__name="admin").first()
    r = admin.patch(reverse("admin-staff-detail", args=[me.id]), {"roles": []}, format="json")
    assert r.json()["error"]["code"] == "self_lockout"
    # admin bo'lmagan xodim kira olmaydi
    assert staff_client("content_manager").get(url).status_code == 403
