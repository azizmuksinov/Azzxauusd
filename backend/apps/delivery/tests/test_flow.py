from decimal import Decimal

import pytest
from django.urls import reverse

from apps.backoffice.models import CashAccount, CashTransaction
from apps.backoffice.services import balance
from apps.core.settings_registry import set_setting
from apps.delivery.models import CodCollection, DeliveryAttempt, RouteStop
from apps.inventory.models import Stock, StockMovement
from apps.notifications.models import NotificationLog

pytestmark = pytest.mark.django_db

INSPECTION = {"packaging_intact": True, "appearance_ok": True, "complete_set": True, "powered_on": True}


def stop_id(route, order):
    return next(s["id"] for s in route["stops"] if s["order"]["number"] == order.number)


def on_hand(variant):
    return sum(s.on_hand for s in Stock.objects.filter(variant=variant))


def deliver(client, sid, payment="cash", **extra):
    return client.post(
        reverse("courier-stop-deliver", args=[sid]),
        {"door_payment": payment, "inspection": INSPECTION, "received_by": "Ali", **extra},
        format="json",
    )


def test_picking_and_packing(make_order, staff):
    order = make_order()
    assert order.status == "cod_confirmed"
    r = staff.get(reverse("admin-order-list"), {"status": "paid,cod_confirmed"})
    assert [o["number"] for o in r.json()["results"]] == [order.number]
    # qadoqlash faqat yig'ishdan keyin
    assert staff.post(reverse("admin-order-pack", args=[order.number]), {}, format="json").status_code == 409
    staff.post(reverse("admin-order-start-picking", args=[order.number]))
    r = staff.post(reverse("admin-order-pack", args=[order.number]), {}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "packed"


def test_cash_delivery_full_flow(make_order, phone_variant, issued_route, courier_client, courier, staff):
    order = make_order()
    stock_before = on_hand(phone_variant)
    route = issued_route(order)
    order.refresh_from_db()
    assert order.status == "handed_to_courier"
    assert on_hand(phone_variant) == stock_before - 1  # tovar ombordan chiqdi

    # kuryer o'z marshrutini ko'radi
    r = courier_client.get(reverse("courier-routes"))
    assert [x["number"] for x in r.json()] == [route["number"]]
    detail = courier_client.get(reverse("courier-route", args=[route["id"]])).json()
    so = detail["stops"][0]["order"]
    assert so["amount_due"] == "3000000.00" and so["recipient_phone"] == "+998901112233"
    assert "Amir Temur" in so["address"]

    sid = stop_id(route, order)
    # yo'lga chiqmasdan yetkazib bo'lmaydi
    assert deliver(courier_client, sid).json()["error"]["code"] == "not_started"
    r = courier_client.post(reverse("courier-stop-start", args=[sid]))
    assert r.status_code == 200 and r.json()["order"]["status"] == "out_for_delivery"
    assert NotificationLog.objects.filter(template_code="courier_on_way").exists()

    # pul olmay "oldindan to'langan" deb yopib bo'lmaydi
    r = deliver(courier_client, sid, payment="prepaid")
    assert r.status_code == 409 and r.json()["error"]["code"] == "payment_required"

    r = deliver(courier_client, sid)
    assert r.status_code == 201, r.json()
    act = r.json()
    assert act["number"].startswith("TA-") and act["door_payment"] == "cash"
    assert act["amount_collected"] == "3000000.00" and act["inspection"]["powered_on"] is True
    order.refresh_from_db()
    assert order.status == "delivered" and order.payment_status == "paid" and order.paid_amount == order.total

    # kuryerda naqd pul
    cash = courier_client.get(reverse("courier-cash")).json()
    assert cash["outstanding"] == "3000000.00" and len(cash["collections"]) == 1
    # ikkinchi marta natija kiritib bo'lmaydi
    assert deliver(courier_client, sid).json()["error"]["code"] == "stop_finished"

    # kassir qabul qiladi
    kassa = CashAccount.objects.create(name="Asosiy kassa", kind="cash")
    r = staff.get(reverse("admin-courier-cash"))
    assert r.json()[0]["amount"] == "3000000.00"
    r = staff.post(
        reverse("admin-cash-handover-list"), {"courier": courier.pk, "account": kassa.pk}, format="json"
    )
    assert r.status_code == 201, r.json()
    assert r.json()["number"].startswith("KN-") and r.json()["orders_count"] == 1
    assert balance(kassa) == Decimal("3000000.00")
    assert CashTransaction.objects.get(account=kassa).category == "courier_cod"
    assert courier_client.get(reverse("courier-cash")).json()["outstanding"] == "0.00"
    # qayta qabul — topshiriladigan pul yo'q
    r = staff.post(
        reverse("admin-cash-handover-list"), {"courier": courier.pk, "account": kassa.pk}, format="json"
    )
    assert r.json()["error"]["code"] == "nothing_to_accept"

    r = staff.post(reverse("admin-route-sheet-close", args=[route["id"]]))
    assert r.json()["status"] == "closed"
    assert not RouteStop.objects.filter(is_open=True).exists()


def test_courier_cash_only_into_cash_account(make_order, issued_route, courier_client, courier, staff):
    order = make_order()
    sid = stop_id(issued_route(order), order)
    courier_client.post(reverse("courier-stop-start", args=[sid]))
    deliver(courier_client, sid)
    bank = CashAccount.objects.create(name="Bank", kind="bank")
    r = staff.post(
        reverse("admin-cash-handover-list"), {"courier": courier.pk, "account": bank.pk}, format="json"
    )
    assert r.json()["error"]["code"] == "account_not_cash"


def test_qr_payment_at_door(make_order, issued_route, courier_client, settings):
    settings.DEMO_MODE = True
    order = make_order()
    sid = stop_id(issued_route(order), order)
    # yo'lga chiqmaguncha QR yo'q
    r = courier_client.post(reverse("courier-stop-qr", args=[sid]), {"provider": "payme"}, format="json")
    assert r.status_code == 409
    courier_client.post(reverse("courier-stop-start", args=[sid]))
    r = courier_client.post(reverse("courier-stop-qr", args=[sid]), {"provider": "payme"}, format="json")
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["amount"] == "3000000.00" and body["payment_url"].startswith("https://")
    assert body["qr_svg"].startswith("<svg")

    # QR to'lanmaguncha "QR" bilan yopib bo'lmaydi
    assert deliver(courier_client, sid, payment="qr").json()["error"]["code"] == "payment_required"
    r = courier_client.post(reverse("courier-stop-demo-qr-pay", args=[sid]))
    assert r.status_code == 200 and r.json()["order"]["amount_due"] == "0.00"
    r = deliver(courier_client, sid, payment="qr")
    assert (
        r.status_code == 201 and r.json()["door_payment"] == "qr" and r.json()["amount_collected"] == "0.00"
    )
    assert not CodCollection.objects.exists()  # naqd pul yo'q — kuryer qarzi yo'q


def test_payme_qr_at_door_receipt_has_goods_only(make_order, issued_route, courier_client, api_client):
    import base64

    order = make_order()
    sid = stop_id(issued_route(order), order)
    courier_client.post(reverse("courier-stop-start", args=[sid]))
    r = api_client.post(
        reverse("webhook-payme"),
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "CheckPerformTransaction",
            "params": {"amount": 300000000, "account": {"order_id": order.number}},
        },
        format="json",
        HTTP_AUTHORIZATION="Basic " + base64.b64encode(b"Paycom:payme-test-key").decode(),
    )
    result = r.json()["result"]
    assert result["allow"] is True
    assert [i["title"] for i in result["detail"]["items"]] != ["Yetkazib berish"]
    assert all(i["title"] != "Yetkazib berish" for i in result["detail"]["items"])


def test_prepaid_online_order(make_order, issued_route, courier_client):
    order = make_order("payme")
    assert order.status == "paid"
    sid = stop_id(issued_route(order), order)
    courier_client.post(reverse("courier-stop-start", args=[sid]))
    r = deliver(courier_client, sid, payment="prepaid")
    assert r.status_code == 201 and r.json()["door_payment"] == "prepaid"


def test_refused_at_door_returns_to_stock(make_order, phone_variant, issued_route, courier_client, staff):
    order = make_order()
    before = on_hand(phone_variant)
    route = issued_route(order)
    sid = stop_id(route, order)
    courier_client.post(reverse("courier-stop-start", args=[sid]))
    r = courier_client.post(
        reverse("courier-stop-refuse", args=[sid]), {"reason": "Rangi yoqmadi"}, format="json"
    )
    assert r.status_code == 200 and r.json()["order"]["status"] == "refused_at_door"
    assert on_hand(phone_variant) == before - 1

    staff.post(reverse("admin-route-sheet-close", args=[route["id"]]))
    order.refresh_from_db()
    assert order.status == "returned"
    assert order.payment_status == "refund_pending"  # yetkazish avansi — moliya hal qiladi
    assert on_hand(phone_variant) == before
    assert StockMovement.objects.filter(reason="return", ref_id=str(order.pk)).count() == 1


def test_three_failed_attempts_then_returned(make_order, phone_variant, issued_route, courier_client, staff):
    order = make_order()
    before = on_hand(phone_variant)
    for n in (1, 2, 3):
        route = issued_route(order)
        sid = stop_id(route, order)
        if n == 2:
            courier_client.post(reverse("courier-stop-start", args=[sid]))
        r = courier_client.post(
            reverse("courier-stop-fail", args=[sid]), {"outcome": "not_home"}, format="json"
        )
        assert r.status_code == 200, r.json()
        assert r.json() == {"attempts": n, "max_attempts": 3, "will_return": n == 3}
        order.refresh_from_db()
        assert order.status == "in_transit"
        staff.post(reverse("admin-route-sheet-close", args=[route["id"]]))
        order.refresh_from_db()
        assert order.status == ("returned" if n == 3 else "in_transit")
    assert DeliveryAttempt.objects.filter(order=order).count() == 3
    assert on_hand(phone_variant) == before
    assert NotificationLog.objects.filter(template_code="courier_failed").count() == 2


def test_attempt_limit_is_a_setting(make_order, issued_route, courier_client, staff, courier, warehouse):
    set_setting("delivery_max_attempts", 1)
    order = make_order()
    route = issued_route(order)
    courier_client.post(
        reverse("courier-stop-fail", args=[stop_id(route, order)]), {"outcome": "no_answer"}, format="json"
    )
    staff.post(reverse("admin-route-sheet-close", args=[route["id"]]))
    order.refresh_from_db()
    assert order.status == "returned"


def test_not_visited_does_not_count_as_attempt(make_order, issued_route, staff):
    order = make_order()
    route = issued_route(order)
    staff.post(reverse("admin-route-sheet-close", args=[route["id"]]))
    order.refresh_from_db()
    assert order.status == "in_transit"
    assert not DeliveryAttempt.objects.exists()
    assert RouteStop.objects.get(order=order).result == "not_visited"
    # keyingi marshrutga qo'shiladi
    route2 = issued_route(order)
    assert route2["stops"][0]["order"]["number"] == order.number


def test_route_rules(make_order, ready, staff, courier, warehouse, fridge_variant):
    from datetime import date

    url = reverse("admin-route-sheet-list")
    base = {"courier": courier.pk, "warehouse": warehouse.pk, "date": str(date.today())}
    not_packed = make_order()
    r = staff.post(url, {**base, "orders": [not_packed.number]}, format="json")
    assert r.json()["error"]["code"] == "order_not_ready"

    order = ready(make_order())
    r = staff.post(url, {**base, "orders": [order.number]}, format="json")
    assert r.status_code == 201
    r = staff.post(url, {**base, "orders": [order.number]}, format="json")
    assert r.json()["error"]["code"] == "already_in_route"

    # yirik tovar — yuk mashinasi kerak
    fridge = ready(make_order(variant=fridge_variant))
    assert fridge.delivery_vehicle == "truck"
    r = staff.post(url, {**base, "orders": [fridge.number]}, format="json")
    assert r.json()["error"]["code"] == "truck_required"

    # bo'sh marshrutni berib bo'lmaydi; qoralamadan nuqta olib tashlanadi
    r = staff.post(url, base, format="json")
    rid = r.json()["id"]
    assert staff.post(reverse("admin-route-sheet-issue", args=[rid])).json()["error"]["code"] == "route_empty"
    r = staff.post(
        reverse("admin-route-sheet-add-stops", args=[rid]), {"orders": [not_packed.number]}, format="json"
    )
    assert r.json()["error"]["code"] == "order_not_ready"


def test_remove_stop_from_draft(make_order, ready, staff, courier, warehouse):
    from datetime import date

    order = ready(make_order())
    r = staff.post(
        reverse("admin-route-sheet-list"),
        {
            "courier": courier.pk,
            "warehouse": warehouse.pk,
            "date": str(date.today()),
            "orders": [order.number],
        },
        format="json",
    )
    route = r.json()
    r = staff.delete(reverse("admin-route-sheet-remove-stop", args=[route["id"], route["stops"][0]["id"]]))
    assert r.status_code == 200 and r.json()["stops"] == []
    r = staff.get(reverse("admin-order-list"), {"status": "packed", "unrouted": "1"})
    assert [o["number"] for o in r.json()["results"]] == [order.number]


def test_courier_sees_only_own_routes(make_order, issued_route, django_user_model, warehouse):
    from django.contrib.auth.models import Group
    from rest_framework.test import APIClient

    from apps.delivery.models import Courier

    order = make_order()
    route = issued_route(order)
    other_user = django_user_model.objects.create_user(phone="+998977770002")
    other_user.groups.add(Group.objects.get(name="courier"))
    Courier.objects.create(user=other_user)
    c = APIClient()
    c.force_authenticate(other_user)
    assert c.get(reverse("courier-routes")).json() == []
    assert c.get(reverse("courier-route", args=[route["id"]])).status_code == 404
    assert c.post(reverse("courier-stop-start", args=[route["stops"][0]["id"]])).status_code == 404


def test_permissions(auth_client, staff_client, make_order):
    assert auth_client.get(reverse("courier-routes")).status_code == 403
    assert auth_client.get(reverse("admin-order-list")).status_code == 403
    support = staff_client("support")
    assert support.get(reverse("admin-order-list")).status_code == 200
    order = make_order()
    assert support.post(reverse("admin-order-start-picking", args=[order.number])).status_code == 403
    assert support.get(reverse("admin-courier-cash")).status_code == 403
    # courier roli bor, lekin profili yo'q
    no_profile = staff_client("courier")
    assert no_profile.get(reverse("courier-me")).status_code == 403


def test_create_courier(staff):
    r = staff.post(
        reverse("admin-courier-list"),
        {"phone": "90 123 45 67", "first_name": "Sardor", "vehicle": "truck"},
        format="json",
    )
    assert r.status_code == 201, r.json()
    assert r.json()["phone"] == "+998901234567" and r.json()["vehicle"] == "truck"
    r = staff.post(
        reverse("admin-courier-list"), {"phone": "+998901234567", "first_name": "X"}, format="json"
    )
    assert r.status_code == 409
