import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.marketing.models import PromoCode
from apps.orders.models import Order

pytestmark = pytest.mark.django_db


def _quote(c, address):
    return c.post(reverse("checkout-delivery"), {"address_id": address.id}, format="json").json()["quote_id"]


def _place(c, address, qid, code="", key=None):
    return c.post(
        reverse("orders"),
        {"address_id": address.id, "quote_id": qid, "payment_method": "cash", "promo_code": code},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )


def test_promo_discounts_goods_not_delivery(client_with_cart, phone_variant, address, tashkent_zone):
    """Promokod tovarlar summasidan chegiradi (yetkazishdan emas); bitta mijoz — bir marta."""
    PromoCode.objects.create(code="YANGI10", kind="percent", value=10, max_discount=Decimal("200000"))
    c = client_with_cart((phone_variant, 1))  # 3 000 000 + yetkazish 25 000
    r = c.post(reverse("promo-check"), {"code": " yangi10 "}, format="json")
    assert r.status_code == 200 and r.json() == {
        "code": "YANGI10",
        "discount": "200000.00",
        "subtotal": "3000000.00",
    }
    qid = _quote(c, address)
    s = c.post(
        reverse("checkout-summary"),
        {"address_id": address.id, "quote_id": qid, "promo_code": "YANGI10"},
        format="json",
    ).json()
    assert (s["discount_total"], s["total"], s["promo_code"]) == ("200000.00", "2825000.00", "YANGI10")
    o = _place(c, address, qid, "yangi10").json()
    assert (o["discount_total"], o["total"], o["promo_code"]) == ("200000.00", "2825000.00", "YANGI10")
    assert Order.objects.get(number=o["number"]).cod_amount == Decimal("2800000")  # yetkazish oldindan
    # ikkinchi marta — yo'q
    c2 = client_with_cart((phone_variant, 1))
    r = c2.post(reverse("promo-check"), {"code": "YANGI10"}, format="json")
    assert r.status_code == 400 and "foydalangansiz" in r.json()["error"]["message"]
    r = _place(c2, address, _quote(c2, address), "YANGI10")
    assert (
        r.status_code == 400 and r.json()["error"]["code"] == "promo_invalid" and Order.objects.count() == 1
    )


def test_promo_rules(client_with_cart, phone_variant, staff_client):
    now = timezone.now()
    PromoCode.objects.create(code="ESKI", kind="amount", value=50000, ends_at=now - timedelta(days=1))
    PromoCode.objects.create(code="KATTA", kind="amount", value=50000, min_subtotal=Decimal("5000000"))
    PromoCode.objects.create(code="OCHIQ", kind="amount", value=50000, is_active=False)
    c = client_with_cart((phone_variant, 1))
    for code, text in [
        ("ESKI", "muddati tugagan"),
        ("KATTA", "5 000 000"),
        ("OCHIQ", "yo'q"),
        ("YOQ", "yo'q"),
    ]:
        r = c.post(reverse("promo-check"), {"code": code}, format="json")
        assert r.status_code == 400 and text in r.json()["error"]["message"], code
    # xodim: yaratish, tekshiruvlar, foydalanish soni
    s = staff_client("content_manager")
    r = s.post(
        reverse("admin-promo-list"), {"code": "bahor-5", "kind": "percent", "value": "5"}, format="json"
    )
    assert r.status_code == 201 and r.json()["code"] == "BAHOR-5" and r.json()["used"] == 0
    assert (
        s.post(
            reverse("admin-promo-list"), {"code": "X", "kind": "percent", "value": "95"}, format="json"
        ).status_code
        == 400
    )
    assert (
        c.post(reverse("promo-check"), {"code": "bahor-5"}, format="json").json()["discount"] == "150000.00"
    )
    assert staff_client("courier").get(reverse("admin-promo-list")).status_code == 403


def test_stock_request_and_quick_order(api_client, staff_client, phone_variant):
    from django.core.cache import cache

    cache.clear()
    r = api_client.post(
        reverse("stock-request"), {"variant_id": phone_variant.id, "phone": "90 123 45 67"}, format="json"
    )
    assert r.status_code == 201 and r.json()["phone"] == "+998901234567"
    again = api_client.post(
        reverse("stock-request"), {"variant_id": phone_variant.id, "phone": "+998901234567"}, format="json"
    )
    assert again.json()["id"] == r.json()["id"]  # takror yozilmaydi
    assert (
        api_client.post(
            reverse("stock-request"), {"variant_id": phone_variant.id, "phone": "123"}, format="json"
        ).status_code
        == 400
    )
    q = api_client.post(
        reverse("quick-order"),
        {"variant_id": phone_variant.id, "phone": "+998 93 555 00 11", "name": "Ali", "qty": 2},
        format="json",
    )
    assert q.status_code == 201
    assert (
        api_client.post(
            reverse("quick-order"), {"variant_id": 999999, "phone": "901234567"}, format="json"
        ).status_code
        == 404
    )

    s = staff_client("support")
    assert s.get(reverse("admin-leads-summary")).json()["quick_orders"] == 1
    row = s.get(reverse("admin-quick-order-list"), {"status": "new"}).json()["results"][0]
    assert (row["phone"], row["qty"], row["name"], row["price"]) == ("+998935550011", 2, "Ali", "3000000.00")
    r = s.post(reverse("admin-quick-order-set-status", args=[row["id"]]), {"status": "done"}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "done"
    assert s.get(reverse("admin-leads-summary")).json()["quick_orders"] == 0
    st = s.get(reverse("admin-stock-request-list")).json()["results"][0]
    assert st["phone"] == "+998901234567" and st["status"] == "new" and "available" in st
    assert (
        s.post(
            reverse("admin-stock-request-set-status", args=[st["id"]]), {"status": "xato"}, format="json"
        ).status_code
        == 400
    )
    assert api_client.get(reverse("admin-quick-order-list")).status_code == 401


def test_installment_plans_in_site_content(staff_client, api_client):
    site = api_client.get(reverse("site-content")).json()
    assert site["installments"]["enabled"] is False and [
        p["months"] for p in site["installments"]["plans"]
    ] == [3, 6, 12]
    s = staff_client("admin")
    body = {
        "installments": {
            "enabled": True,
            "plans": [{"months": 12, "percent": 28}, {"months": 6, "percent": "12.5"}, {"months": 0}, "x"],
        }
    }
    r = s.put(reverse("admin-site-content"), body, format="json")
    assert r.status_code == 200, r.json()
    got = api_client.get(reverse("site-content")).json()["installments"]
    assert got["enabled"] is True and got["plans"] == [
        {"months": 6, "percent": 12.5},
        {"months": 12, "percent": 28.0},
    ]
