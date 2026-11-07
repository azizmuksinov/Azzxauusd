import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.settings_registry import set_setting
from apps.inventory.models import Reservation, Stock
from apps.logistics.models import DeliveryQuote
from apps.orders.models import Order
from apps.orders.services import cancel_unpaid_orders

pytestmark = pytest.mark.django_db


def quote(client, address, **extra):
    return client.post(reverse("checkout-delivery"), {"address_id": address.id, **extra}, format="json")


def place(client, address, quote_id, method="cash", lifting=False, key=None):
    return client.post(
        reverse("orders"),
        {"address_id": address.id, "quote_id": quote_id, "payment_method": method, "lifting": lifting},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )


def test_small_parcel_quote(client_with_cart, phone_variant, address, tashkent_zone):
    c = client_with_cart((phone_variant, 2))  # 1 kg
    resp = quote(c, address)
    assert resp.status_code == 200, resp.json()
    q = resp.json()
    assert q["provider"] == "own" and q["delivery_price"] == "25000.00"
    assert q["eta_days_min"] == 1 and q["lifting"] == {"available": False, "price": None}


def test_heavier_parcel_uses_next_weight_bracket(client_with_cart, phone_variant, address, tashkent_zone):
    phone_variant.weight_kg = Decimal("3")
    phone_variant.save()
    assert quote(client_with_cart((phone_variant, 2)), address).json()["delivery_price"] == "40000.00"


def test_bulky_uses_truck_and_lifting(client_with_cart, fridge_variant, address, tashkent_zone):
    c = client_with_cart((fridge_variant, 1))
    assert quote(c, address).json()["lifting"]["available"] is False  # narx sozlanmagan — xizmat yo'q
    set_setting("lifting_price_per_floor", "20000")
    q = quote(c, address).json()
    assert q["delivery_price"] == "120000.00"
    assert q["lifting"] == {"available": True, "price": "80000.00"}  # 5-qavat, liftsiz: 4 qavat * 20 000


def test_lifting_with_elevator(client_with_cart, fridge_variant, address, tashkent_zone):
    set_setting("lifting_price_with_elevator", "50000")
    address.elevator = "freight"
    address.save()
    assert quote(client_with_cart((fridge_variant, 2)), address).json()["lifting"]["price"] == "100000.00"


def test_no_zone_means_unavailable(client_with_cart, phone_variant, address):
    resp = quote(client_with_cart((phone_variant, 1)), address)
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "delivery_unavailable"


def test_empty_cart(auth_client, address, tashkent_zone):
    assert quote(auth_client, address).json()["error"]["code"] == "cart_empty"


def test_foreign_address(client_with_cart, phone_variant, tashkent_zone, django_user_model):
    from apps.accounts.models import Address

    other = django_user_model.objects.create_user(phone="+998935550000")
    addr = Address.objects.create(
        user=other, district_id=1, street="x", house="1", recipient_name="b", recipient_phone="+998935550000"
    )
    assert quote(client_with_cart((phone_variant, 1)), addr).status_code == 404


def test_summary_payment_options(client_with_cart, phone_variant, address, tashkent_zone):
    c = client_with_cart((phone_variant, 1))
    qid = quote(c, address).json()["quote_id"]
    data = c.post(
        reverse("checkout-summary"), {"address_id": address.id, "quote_id": qid}, format="json"
    ).json()
    assert data["total"] == "3025000.00"
    methods = {m["code"]: m for m in data["payment_methods"]}
    # yetkazish narxi (25 000) eshikda to'lovda ham oldindan onlayn
    assert methods["cash"]["available"] and methods["cash"]["required_prepayment"] == "25000.00"
    assert methods["payme"]["required_prepayment"] == "3025000.00"

    set_setting("cod_max_amount", "2000000")
    data = c.post(
        reverse("checkout-summary"), {"address_id": address.id, "quote_id": qid}, format="json"
    ).json()
    methods = {m["code"]: m for m in data["payment_methods"]}
    assert methods["cash"]["available"] is False

    set_setting("cod_prepayment_percent", 30)
    data = c.post(
        reverse("checkout-summary"), {"address_id": address.id, "quote_id": qid}, format="json"
    ).json()
    methods = {m["code"]: m for m in data["payment_methods"]}
    assert methods["cash"]["available"] and methods["cash"]["required_prepayment"] == "907500.00"


def test_place_cod_order(client_with_cart, phone_variant, address, tashkent_zone, user):
    c = client_with_cart((phone_variant, 2))
    qid = quote(c, address).json()["quote_id"]
    resp = place(c, address, qid, "cash")
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["status"] == "created" and data["total"] == "6025000.00"
    assert data["required_prepayment"] == "25000.00" and data["cod_amount"] == "6000000.00"
    assert data["amount_to_pay_online"] == "25000.00" and data["payment_deadline"] is not None
    assert data["address_snapshot"]["floor"] == 5 and data["items"][0]["qty"] == 2
    assert data["number"].endswith(f"{Order.objects.get().pk:07d}")
    assert [h["to_status"] for h in data["history"]] == ["created"]

    stock = Stock.objects.get(variant=phone_variant)
    assert stock.reserved == 2
    assert c.get(reverse("cart")).json()["items"] == []  # savat tozalandi
    assert DeliveryQuote.objects.get(public_id=qid).used_at is not None
    assert Order.objects.get().items.get().cost_price == phone_variant.cost_price  # marja uchun snapshot


def test_place_online_order_has_deadline(client_with_cart, phone_variant, address, tashkent_zone):
    c = client_with_cart((phone_variant, 1))
    data = place(c, address, quote(c, address).json()["quote_id"], "payme").json()
    assert data["cod_amount"] == "0.00" and data["amount_to_pay_online"] == "3025000.00"
    assert data["payment_deadline"] is not None


def test_idempotency(client_with_cart, phone_variant, address, tashkent_zone):
    c = client_with_cart((phone_variant, 1))
    qid = quote(c, address).json()["quote_id"]
    key = str(uuid.uuid4())
    first = place(c, address, qid, key=key)
    second = place(c, address, qid, key=key)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["number"] == second.json()["number"] and Order.objects.count() == 1


def test_idempotency_key_required(client_with_cart, phone_variant, address, tashkent_zone):
    c = client_with_cart((phone_variant, 1))
    resp = c.post(
        reverse("orders"),
        {"address_id": address.id, "quote_id": str(uuid.uuid4()), "payment_method": "cash"},
        format="json",
    )
    assert resp.json()["error"]["code"] == "idempotency_key_required"


@pytest.mark.parametrize("change", ["cart", "address", "expired", "reuse"])
def test_quote_invalidation(client_with_cart, phone_variant, address, tashkent_zone, change):
    c = client_with_cart((phone_variant, 1))
    qid = quote(c, address).json()["quote_id"]
    if change == "cart":
        c.post(reverse("cart-items"), {"variant_id": phone_variant.id, "qty": 1}, format="json")
    elif change == "address":
        address.floor = 9
        address.save()
    elif change == "expired":
        DeliveryQuote.objects.filter(public_id=qid).update(expires_at=timezone.now() - timedelta(seconds=1))
    elif change == "reuse":
        assert place(c, address, qid).status_code == 201
        c.post(reverse("cart-items"), {"variant_id": phone_variant.id, "qty": 1}, format="json")
    resp = place(c, address, qid)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "quote_expired"


def test_lifting_requested_but_unavailable(client_with_cart, phone_variant, address, tashkent_zone):
    c = client_with_cart((phone_variant, 1))
    resp = place(c, address, quote(c, address).json()["quote_id"], lifting=True)
    assert resp.json()["error"]["code"] == "lifting_unavailable"


def test_lifting_added_to_total(client_with_cart, fridge_variant, address, tashkent_zone):
    set_setting("lifting_price_per_floor", "20000")
    c = client_with_cart((fridge_variant, 1))
    data = place(c, address, quote(c, address).json()["quote_id"], lifting=True).json()
    assert data["lifting_fee"] == "80000.00" and data["total"] == "8200000.00"


def test_cod_above_limit_rejected(client_with_cart, phone_variant, address, tashkent_zone):
    set_setting("cod_max_amount", "1000000")
    c = client_with_cart((phone_variant, 1))
    resp = place(c, address, quote(c, address).json()["quote_id"], "cash")
    assert resp.json()["error"]["code"] == "payment_method_unavailable"


def test_cod_with_prepayment(client_with_cart, phone_variant, address, tashkent_zone):
    set_setting("cod_max_amount", "1000000")
    set_setting("cod_prepayment_percent", 20)
    c = client_with_cart((phone_variant, 1))
    data = place(c, address, quote(c, address).json()["quote_id"], "cash").json()
    assert data["required_prepayment"] == "605000.00" and data["cod_amount"] == "2420000.00"
    assert data["payment_deadline"] is not None  # avans onlayn to'lanishi kerak


def test_out_of_stock_at_order_time(client_with_cart, phone_variant, address, tashkent_zone):
    c = client_with_cart((phone_variant, 2))
    qid = quote(c, address).json()["quote_id"]
    Stock.objects.filter(variant=phone_variant).update(on_hand=1)
    resp = place(c, address, qid)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "cart_has_problems"
    assert not Order.objects.exists()


def test_cancel_releases_stock(client_with_cart, phone_variant, address, tashkent_zone):
    c = client_with_cart((phone_variant, 2))
    number = place(c, address, quote(c, address).json()["quote_id"]).json()["number"]
    resp = c.post(reverse("order-cancel", args=[number]), {"reason": "fikrim o'zgardi"}, format="json")
    assert resp.status_code == 200 and resp.json()["status"] == "cancelled"
    assert Stock.objects.get(variant=phone_variant).reserved == 0
    resp = c.post(reverse("order-cancel", args=[number]), {"reason": "yana"}, format="json")
    assert resp.status_code == 409


def test_cancel_after_packed_forbidden(client_with_cart, phone_variant, address, tashkent_zone):
    from apps.orders.state import transition

    c = client_with_cart((phone_variant, 1))
    number = place(c, address, quote(c, address).json()["quote_id"]).json()["number"]
    order = Order.objects.get(number=number)
    for s in ["cod_confirmed", "picking", "packed"]:
        order = transition(order, s, actor_type="staff")
    resp = c.post(reverse("order-cancel", args=[number]), {"reason": "x"}, format="json")
    assert resp.json()["error"]["code"] == "cannot_cancel"


def test_unpaid_online_orders_cancelled(client_with_cart, phone_variant, address, tashkent_zone):
    c = client_with_cart((phone_variant, 1))
    number = place(c, address, quote(c, address).json()["quote_id"], "click").json()["number"]
    assert cancel_unpaid_orders() == 0
    assert cancel_unpaid_orders(now=timezone.now() + timedelta(minutes=31)) == 1
    order = Order.objects.get(number=number)
    assert order.status == "cancelled" and order.cancel_reason == "payment_timeout"
    assert Reservation.objects.get(ref_id=str(order.pk)).status == "released"


def test_orders_list_and_privacy(client_with_cart, phone_variant, address, tashkent_zone, django_user_model):
    c = client_with_cart((phone_variant, 1))
    number = place(c, address, quote(c, address).json()["quote_id"]).json()["number"]
    data = c.get(reverse("orders"), {"status": "active"}).json()
    assert [o["number"] for o in data["results"]] == [number]
    assert c.get(reverse("orders"), {"status": "completed"}).json()["results"] == []

    from rest_framework.test import APIClient

    stranger = APIClient()
    stranger.force_authenticate(django_user_model.objects.create_user(phone="+998935551111"))
    assert stranger.get(reverse("order-detail", args=[number])).status_code == 404


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_parallel_orders_from_same_cart(user, phone_variant, address, tashkent_zone):
    """Bitta savat/quote bilan bir vaqtda 3 ta so'rov (turli kalitlar): faqat bitta buyurtma yaratiladi."""
    import threading

    from django.db import connection
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user)
    c.post(reverse("cart-items"), {"variant_id": phone_variant.id, "qty": 1}, format="json")
    qid = quote(c, address).json()["quote_id"]
    codes = []
    barrier = threading.Barrier(3)

    def worker():
        client = APIClient()
        client.force_authenticate(user)
        barrier.wait()
        try:
            codes.append(place(client, address, qid).status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes)[0] == 201 and codes.count(201) == 1
    assert Order.objects.count() == 1
    assert Stock.objects.get(variant=phone_variant).reserved == 1


def test_delivery_prepaid_can_be_disabled(client_with_cart, phone_variant, address, tashkent_zone):
    set_setting("delivery_fee_prepaid", False)
    c = client_with_cart((phone_variant, 1))
    data = place(c, address, quote(c, address).json()["quote_id"], "cash").json()
    assert data["required_prepayment"] == "0.00" and data["cod_amount"] == "3025000.00"
    assert data["payment_deadline"] is None
