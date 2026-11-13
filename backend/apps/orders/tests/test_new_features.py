"""Bonus, "birga arzonroq", kun tovari, olib ketish, buyurtmani kuzatish, savol-javob, sotuv hisoboti."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.backoffice.models import CashAccount, CashTransaction
from apps.catalog.tests import factories as f
from apps.core.settings_registry import set_setting
from apps.delivery.tests.conftest import prepay
from apps.logistics.models import PickupPoint
from apps.marketing import bonus, deals
from apps.marketing.models import BonusEntry, Deal
from apps.orders.models import Order, OrderStatus
from apps.orders.state import transition
from apps.reviews.models import Question

pytestmark = pytest.mark.django_db
S = OrderStatus


def _quote(c, address):
    return c.post(reverse("checkout-delivery"), {"address_id": address.id}, format="json").json()["quote_id"]


def _place(c, body):
    return c.post(reverse("orders"), body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))


def _deliver(order: Order, staff) -> Order:
    """Yetkazishli buyurtmani oxirigacha olib borish (holatlar zanjiri)."""
    order = prepay(order)
    for to in (S.PICKING, S.PACKED, S.HANDED_TO_COURIER, S.OUT_FOR_DELIVERY, S.DELIVERED):
        order = transition(order, to, actor_type="staff", actor=staff)
    return order


@pytest.fixture
def point():
    return PickupPoint.objects.create(name="Chilonzor do'koni", address="Chilonzor 5", hours="9:00–20:00")


# ------------------------------------------------------------------ bonus
def test_bonus_is_earned_on_delivery_spent_at_checkout_and_returned_on_cancel(
    client_with_cart, phone_variant, address, tashkent_zone, user, staff_client
):
    staff = staff_client("admin").user
    c = client_with_cart((phone_variant, 1))  # 3 000 000 + yetkazish 25 000
    # Tizim o'chiq (foiz kiritilmagan): bonus yozilmaydi, sarflab ham bo'lmaydi.
    assert c.get(reverse("my-bonus")).json()["enabled"] is False
    set_setting("bonus_earn_percent", Decimal("2"))
    set_setting("bonus_max_pay_percent", 30)

    order = Order.objects.get(
        number=_place(
            c, {"address_id": address.id, "quote_id": _quote(c, address), "payment_method": "cash"}
        ).json()["number"]
    )
    assert bonus.balance(user) == 0  # yetkazilmaguncha yozilmaydi
    order = _deliver(order, staff)
    assert order.bonus_earned == Decimal("60000") and bonus.balance(user) == Decimal("60000")
    transition_again = BonusEntry.objects.filter(order=order, kind="earn").count()
    assert bonus.earn(order) == Decimal("60000") and transition_again == 1  # takror yozilmaydi
    me = c.get(reverse("my-bonus")).json()
    assert me["balance"] == "60000.00" and me["history"][0]["kind"] == "earn"

    # Keyingi xarid: bonus bilan to'lash (tovarlar summasining 30% idan oshmaydi, yetkazishga tegmaydi).
    c2 = client_with_cart((phone_variant, 1))
    qid = _quote(c2, address)
    body = {"address_id": address.id, "quote_id": qid, "use_bonus": True}
    s = c2.post(reverse("checkout-summary"), body, format="json").json()
    assert (s["bonus_spent"], s["total"]) == ("60000.00", "2965000.00")
    assert s["bonus"] == {
        "enabled": True,
        "balance": "60000.00",
        "usable": "60000.00",
        "will_earn": "58800.00",
    }
    o2 = _place(c2, {**body, "payment_method": "cash"}).json()
    assert (o2["bonus_spent"], o2["total"]) == ("60000.00", "2965000.00")
    assert bonus.balance(user) == 0
    # Bekor qilinsa — sarflangan bonus qaytadi (bir marta).
    order2 = Order.objects.get(number=o2["number"])
    transition(order2, S.CANCELLED, actor_type="customer", actor=user)
    bonus.refund(order2)
    assert bonus.balance(user) == Decimal("60000")


def test_bonus_cap_and_admin_adjust(
    client_with_cart, phone_variant, address, tashkent_zone, user, staff_client
):
    set_setting("bonus_earn_percent", Decimal("5"))
    set_setting("bonus_max_pay_percent", 10)
    admin = staff_client("admin")
    url = reverse("admin-bonus-adjust")
    r = admin.post(url, {"phone": user.phone, "amount": "1000000", "note": "Sovg'a"}, format="json")
    assert r.status_code == 201 and r.json()["balance"] == "1000000.00"
    assert (
        admin.post(url, {"phone": user.phone, "amount": "-2000000", "note": "x"}, format="json").status_code
        == 400
    )
    assert (
        admin.post(url, {"phone": "+998900000099", "amount": "5", "note": "x"}, format="json").status_code
        == 404
    )
    assert staff_client("content_manager").post(url, {}, format="json").status_code == 403
    assert admin.get(reverse("admin-bonus-list"), {"phone": user.phone[-7:]}).json()["count"] == 1
    c = client_with_cart((phone_variant, 1))
    body = {"address_id": address.id, "quote_id": _quote(c, address), "use_bonus": True}
    s = c.post(reverse("checkout-summary"), body, format="json").json()
    assert s["bonus_spent"] == "300000.00"  # 3 000 000 ning 10% i, balans esa 1 000 000


# ------------------------------------------------------------------ birga arzonroq
def test_bundle_discount_in_cart_checkout_and_product_page(
    client_with_cart, phone_variant, address, tashkent_zone, staff_client
):
    case = f.product(f.category(), price="200000").variants.first()
    f.stock(case, 5)
    s = staff_client("content_manager")
    r = s.post(
        reverse("admin-bundle-list"),
        {"product": phone_variant.product_id, "extra": case.product_id, "discount_percent": "25"},
        format="json",
    )
    assert r.status_code == 201, r.json()
    same = {"product": case.product_id, "extra": case.product_id, "discount_percent": "10"}
    assert s.post(reverse("admin-bundle-list"), same, format="json").status_code == 400

    offers = APIClient().get(reverse("product-bundles", args=[phone_variant.product.slug])).json()
    assert len(offers) == 1 and (offers[0]["bundle_price"], offers[0]["save"]) == ("150000.00", "50000.00")
    assert offers[0]["product"]["variant_id"] == case.id

    # Bitta telefon — bitta g'ilofga chegirma; ikkinchi g'ilof to'liq narxda.
    c = client_with_cart((phone_variant, 1), (case, 2))
    cart = c.get(reverse("cart")).json()
    assert (cart["subtotal"], cart["bundle_discount"], cart["total"]) == ("3400000.00", "50000", "3350000.00")
    assert cart["bundles"][0]["qty"] == 1 and cart["bundles"][0]["percent"] == "25"
    qid = _quote(c, address)
    o = _place(c, {"address_id": address.id, "quote_id": qid, "payment_method": "cash"}).json()
    assert (o["discount_total"], o["total"]) == ("50000.00", "3375000.00")  # + yetkazish 25 000
    # Asosiy tovarsiz chegirma yo'q.
    alone = client_with_cart((case, 1)).get(reverse("cart")).json()
    assert alone["bundle_discount"] == "0"


# ------------------------------------------------------------------ kun tovari
def test_deal_changes_price_for_its_period_and_restores_it(phone_variant, staff_client):
    s = staff_client("content_manager")
    url = reverse("admin-deal-list")
    now = timezone.now()
    bad = {"variant": phone_variant.id, "price": "3500000", "ends_at": (now + timedelta(hours=5)).isoformat()}
    assert s.post(url, bad, format="json").json()["error"]["code"] == "deal_price"
    r = s.post(url, {**bad, "price": "2500000"}, format="json")
    assert r.status_code == 201 and r.json()["state"] == "active", r.json()
    phone_variant.refresh_from_db()
    assert (phone_variant.price, phone_variant.old_price) == (Decimal("2500000"), Decimal("3000000"))
    assert s.post(url, {**bad, "price": "2400000"}, format="json").json()["error"]["code"] == "deal_overlap"

    live = APIClient().get(reverse("deals")).json()
    assert len(live) == 1 and live[0]["product"]["price"] == "2500000.00"
    assert live[0]["product"]["variant_id"] == phone_variant.id and live[0]["ends_at"]

    # Muddat tugadi: narx avvalgisiga qaytadi, aksiya ro'yxatdan chiqadi.
    assert deals.sync(now + timedelta(hours=6)) == 1
    phone_variant.refresh_from_db()
    assert (phone_variant.price, phone_variant.old_price) == (Decimal("3000000"), None)
    assert Deal.objects.get().state == "ended" and APIClient().get(reverse("deals")).json() == []


def test_scheduled_deal_starts_later_and_cancel_restores_price(phone_variant, staff_client):
    s = staff_client("content_manager")
    now = timezone.now()
    body = {
        "variant": phone_variant.id,
        "price": "2700000",
        "starts_at": (now + timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(hours=3)).isoformat(),
    }
    deal_id = s.post(reverse("admin-deal-list"), body, format="json").json()["id"]
    phone_variant.refresh_from_db()
    assert phone_variant.price == Decimal("3000000") and Deal.objects.get().state == "scheduled"
    deals.sync(now + timedelta(hours=2))
    phone_variant.refresh_from_db()
    assert phone_variant.price == Decimal("2700000")
    assert s.delete(reverse("admin-deal-detail", args=[deal_id])).status_code == 204
    phone_variant.refresh_from_db()
    assert phone_variant.price == Decimal("3000000") and Deal.objects.get().state == "cancelled"


# ------------------------------------------------------------------ olib ketish
def test_pickup_order_is_free_to_collect_and_handed_over_by_staff(
    client_with_cart, phone_variant, point, user, staff_client
):
    assert APIClient().get(reverse("pickup-points")).json()[0]["name"] == "Chilonzor do'koni"
    c = client_with_cart((phone_variant, 1))
    body = {"pickup_point_id": point.id}
    s = c.post(reverse("checkout-summary"), body, format="json").json()
    assert (s["delivery_fee"], s["total"]) == ("0", "3000000.00") and s["delivery"]["pickup_point"]["address"]
    cash = next(m for m in s["payment_methods"] if m["code"] == "cash")
    assert cash["available"] and cash["required_prepayment"] == "0.00"  # joyida to'lanadi
    assert (
        c.post(reverse("checkout-summary"), {}, format="json").status_code == 400
    )  # manzil ham, punkt ham yo'q

    o = _place(c, {**body, "payment_method": "cash", "recipient_name": "Vali"}).json()
    assert o["is_pickup"] and o["status"] == "cod_confirmed" and o["delivery_fee"] == "0.00"
    assert o["address_snapshot"]["name"] == "Chilonzor do'koni" and o["recipient_name"] == "Vali"
    order = Order.objects.get(number=o["number"])

    wh = staff_client("warehouse")
    detail = reverse("admin-order-detail", args=[order.number])
    assert wh.get(reverse("admin-order-list"), {"pickup": 1}).json()["count"] == 1
    assert (
        wh.get(reverse("admin-order-list"), {"unrouted": 1, "status": "cod_confirmed"}).json()["count"] == 0
    )
    hand = reverse("admin-order-hand-over", args=[order.number])
    assert wh.post(hand, {}, format="json").json()["error"]["code"] == "not_ready"
    assert wh.post(f"{detail}/start-picking").status_code == 200
    assert wh.post(f"{detail}/pack", {"serials": {}}, format="json").status_code == 200
    # Kuryerga berib bo'lmaydi; to'lov olinmaguncha topshirilmaydi.
    with pytest.raises(Exception, match="olib ketadi"):
        transition(order, S.HANDED_TO_COURIER, actor_type="staff")
    assert wh.post(hand, {}, format="json").json()["error"]["code"] == "payment_required"
    till = CashAccount.objects.create(name="Kassa", kind="cash")
    r = wh.post(hand, {"account": till.id}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "delivered", r.json()
    order.refresh_from_db()
    assert order.paid_amount == Decimal("3000000") and order.payment_status == "paid"
    assert CashTransaction.objects.get().amount == Decimal("3000000")
    phone_variant.refresh_from_db()
    from apps.inventory.services import available_by_variant

    assert available_by_variant([phone_variant.id])[phone_variant.id] == 4  # tovar ombordan chiqdi


# ------------------------------------------------------------------ kuzatish
def test_order_is_tracked_by_number_and_phone_without_login(
    client_with_cart, phone_variant, address, tashkent_zone
):
    c = client_with_cart((phone_variant, 1))
    number = _place(
        c, {"address_id": address.id, "quote_id": _quote(c, address), "payment_method": "cash"}
    ).json()["number"]
    anon = APIClient()
    url = reverse("order-track")
    r = anon.post(url, {"number": number, "phone": "90 111 22 33"}, format="json")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert (
        data["status"] == "created"
        and data["items"][0]["qty"] == 1
        and data["history"][0]["status"] == "created"
    )
    assert "address_snapshot" not in data and "recipient_name" not in data  # shaxsiy ma'lumot berilmaydi
    assert anon.post(url, {"number": number, "phone": "+998900000000"}, format="json").status_code == 404
    assert anon.post(url, {"number": "99-0000001", "phone": "90 111 22 33"}, format="json").status_code == 404
    for _ in range(30):
        anon.post(url, {"number": "x", "phone": "1"}, format="json")
    assert anon.post(url, {"number": number, "phone": "90 111 22 33"}, format="json").status_code == 429


# ------------------------------------------------------------------ savol-javob
def test_question_is_shown_after_staff_answers(phone_variant, auth_client, staff_client):
    slug = phone_variant.product.slug
    url = reverse("product-questions", args=[slug])
    anon = APIClient()
    assert anon.post(url, {"text": "ok?"}, format="json").status_code == 400  # juda qisqa
    r = anon.post(url, {"text": "Kafolati necha yil?", "name": "Sardor"}, format="json")
    assert r.status_code == 201 and r.json()["status"] == "new"
    mine = auth_client.post(url, {"text": "Rangi qora bormi?"}, format="json").json()
    assert anon.get(url).json() == []  # javobsiz savol ko'rinmaydi
    assert [q["id"] for q in auth_client.get(url).json()] == [mine["id"]]  # o'z savoli ko'rinadi

    s = staff_client("support")
    assert s.get(reverse("admin-question-summary")).json() == {"new": 2}
    rows = s.get(reverse("admin-question-list"), {"status": "new"}).json()["results"]
    first = next(q for q in rows if q["author"] == "Sardor")
    detail = reverse("admin-question-detail", args=[first["id"]])
    assert s.patch(detail, {"status": "answered"}, format="json").status_code == 400  # javobsiz
    r = s.patch(detail, {"answer": "1 yil rasmiy kafolat."}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "answered"
    shown = anon.get(url).json()
    assert (
        len(shown) == 1 and shown[0]["answer"] == "1 yil rasmiy kafolat." and shown[0]["author"] == "Sardor"
    )
    s.patch(detail, {"status": "hidden"}, format="json")
    assert anon.get(url).json() == [] and Question.objects.get(pk=first["id"]).answer  # javob saqlanadi
    assert staff_client("warehouse").get(reverse("admin-question-list")).status_code == 403


# ------------------------------------------------------------------ hisobot
def test_sales_report_counts_sold_orders_and_abandoned_carts(
    client_with_cart, phone_variant, fridge_variant, address, tashkent_zone, user, staff_client
):
    phone_variant.cost_price = Decimal("2500000")
    phone_variant.save()
    c = client_with_cart((phone_variant, 2))
    o1 = _place(
        c, {"address_id": address.id, "quote_id": _quote(c, address), "payment_method": "cash"}
    ).json()
    c = client_with_cart((fridge_variant, 1))
    o2 = _place(
        c, {"address_id": address.id, "quote_id": _quote(c, address), "payment_method": "payme"}
    ).json()
    transition(Order.objects.get(number=o2["number"]), S.CANCELLED, actor_type="customer", actor=user)
    # Tashlab ketilgan savat: bir kundan ko'p tegilmagan.
    from apps.cart.models import Cart, CartItem

    cart = Cart.objects.create()
    CartItem.objects.create(cart=cart, variant=phone_variant, qty=1)
    Cart.objects.filter(pk=cart.pk).update(updated_at=timezone.now() - timedelta(days=2))

    r = staff_client("finance").get(reverse("admin-sales-report"), {"days": 7})
    assert r.status_code == 200, r.json()
    d = r.json()
    t = d["totals"]
    assert (t["orders"], t["revenue"], t["avg_check"], t["units"]) == (1, "6025000", "6025000", 2)
    assert (t["cancelled"], t["new_customers"], t["gross_profit"]) == (1, 1, "1000000")
    assert len(d["daily"]) == 7 and d["daily"][-1] == {"date": d["to"], "orders": 1, "revenue": "6025000"}
    assert d["top_products"][0]["qty"] == 2 and d["top_products"][0]["revenue"] == "6000000"
    assert d["payment_methods"] == [{"code": "cash", "orders": 1, "revenue": "6025000"}]
    assert d["abandoned_carts"] == {"carts": 1, "value": "3000000"}
    assert o1["number"] and staff_client("warehouse").get(reverse("admin-sales-report")).status_code == 403
