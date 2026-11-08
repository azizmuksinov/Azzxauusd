import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_site_content_defaults_and_admin_update(api_client, staff_client):
    d = api_client.get(reverse("site-content")).json()
    assert d["store_name"] == "TexnoDo'kon" and [s["key"] for s in d["home_sections"]][0] == "hero"
    assert set(d["pages"]) == {"how-to-order", "delivery", "returns", "about"}

    c = staff_client("content_manager")
    url = reverse("admin-site-content")
    r = c.put(
        url,
        {
            "phone": "+998 71 200-00-00",
            "announcement": {"enabled": True, "text": {"uz": "Bepul yetkazish!"}, "color": "red", "junk": 1},
            "home_sections": [
                {"key": "popular", "enabled": True, "title": {"uz": "Xitlar"}},
                {"key": "deals", "enabled": False},
                {"key": "nope"},
            ],
            "pages": {"delivery": {"body": {"uz": "Toshkent bo'ylab 1 kunda."}}},
            "unknown": "x",
        },
        format="json",
    )
    assert r.status_code == 200, r.json()
    d = api_client.get(reverse("site-content")).json()
    assert d["phone"] == "+998 71 200-00-00" and "unknown" not in d
    assert d["announcement"] == {
        "enabled": True,
        "text": {"uz": "Bepul yetkazish!", "ru": ""},
        "link": "",
        "color": "#5b21b6",
    }
    assert [(s["key"], s["enabled"]) for s in d["home_sections"]][:3] == [
        ("popular", True),
        ("deals", False),
        ("hero", True),
    ]
    assert d["home_sections"][0]["title"]["uz"] == "Xitlar"
    assert d["pages"]["delivery"]["body"]["uz"] == "Toshkent bo'ylab 1 kunda."
    assert d["pages"]["delivery"]["title"]["uz"] == "Yetkazish va to'lov"  # standart saqlandi
    # boshqa bo'limlar tegmagan
    c.put(url, {"email": "info@example.uz"}, format="json")
    assert api_client.get(reverse("site-content")).json()["phone"] == "+998 71 200-00-00"
    assert staff_client("courier").put(url, {"email": "x"}, format="json").status_code == 403
