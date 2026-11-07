import uuid
from datetime import date

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.tests import factories as f
from apps.delivery.models import Courier
from apps.orders.models import Order
from apps.orders.tests.conftest import address, client_with_cart, fridge_variant, phone_variant, tashkent_zone  # noqa: F401
from apps.payments.models import Payment, Provider
from apps.payments.services import amount_due, mark_succeeded


@pytest.fixture(autouse=True)
def provider_keys(settings):
    settings.PAYME = {**settings.PAYME, "MERCHANT_ID": "m-123", "KEY": "payme-test-key"}


def prepay(order: Order) -> Order:
    """Yetkazish narxini (avans) onlayn to'langan qilish."""
    p = Payment.objects.create(
        order=order, provider=Provider.DEMO, provider_txn_id=f"t-{uuid.uuid4()}", amount=amount_due(order)
    )
    mark_succeeded(p)
    order.refresh_from_db()
    return order


@pytest.fixture
def make_order(client_with_cart, phone_variant, address, tashkent_zone):  # noqa: F811
    """make_order("cash") -> to'lov (avans) qilingan buyurtma: telefon 3 000 000 + yetkazish 25 000."""

    def make(method="cash", variant=None, qty=1, paid=True):
        c = client_with_cart((variant or phone_variant, qty))
        qid = c.post(reverse("checkout-delivery"), {"address_id": address.id}, format="json").json()[
            "quote_id"
        ]
        resp = c.post(
            reverse("orders"),
            {"address_id": address.id, "quote_id": qid, "payment_method": method},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert resp.status_code == 201, resp.json()
        order = Order.objects.get(number=resp.json()["number"])
        return prepay(order) if paid else order

    return make


@pytest.fixture
def warehouse():
    return f.warehouse()


@pytest.fixture
def staff(staff_client):
    return staff_client("warehouse", "logistics_manager", "finance")


@pytest.fixture
def courier(django_user_model, warehouse):
    u = django_user_model.objects.create_user(phone="+998977770001", first_name="Bobur")
    u.groups.add(Group.objects.get(name="courier"))
    return Courier.objects.create(user=u, warehouse=warehouse)


@pytest.fixture
def courier_client(courier):
    c = APIClient()
    c.force_authenticate(courier.user)
    return c


@pytest.fixture
def ready(staff):
    """ready(order) -> yig'ilgan va qadoqlangan buyurtma."""

    def make(order):
        assert staff.post(reverse("admin-order-start-picking", args=[order.number])).status_code == 200
        r = staff.post(reverse("admin-order-pack", args=[order.number]), {}, format="json")
        assert r.status_code == 200, r.json()
        order.refresh_from_db()
        return order

    return make


@pytest.fixture
def issued_route(staff, courier, warehouse, ready):
    """issued_route(*orders) -> kuryerga berilgan marshrut (dict javob)."""

    def make(*orders):
        numbers = [ready(o).number if o.status in ("paid", "cod_confirmed") else o.number for o in orders]
        r = staff.post(
            reverse("admin-route-sheet-list"),
            {"courier": courier.pk, "warehouse": warehouse.pk, "date": str(date.today()), "orders": numbers},
            format="json",
        )
        assert r.status_code == 201, r.json()
        r = staff.post(reverse("admin-route-sheet-issue", args=[r.json()["id"]]))
        assert r.status_code == 200, r.json()
        return r.json()

    return make
