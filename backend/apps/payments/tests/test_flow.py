import pytest
from django.urls import reverse

from apps.inventory.models import Reservation
from apps.orders.services import cancel_unpaid_orders
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db


def test_demo_pay_only_in_demo(make_order, settings):
    order = make_order("payme")
    url = reverse("order-demo-pay", args=[order.number])
    assert order.client.post(url).status_code == 404
    settings.DEMO_MODE = True
    resp = order.client.post(url)
    assert resp.status_code == 200 and resp.json()["status"] == "paid"
    assert Reservation.objects.get(ref_id=str(order.pk)).expires_at is None  # to'langan — band muddatsiz
    assert order.client.post(url).json()["error"]["code"] == "order_not_payable"


def test_pending_payment_blocks_auto_cancel(make_order):
    from datetime import timedelta

    from django.utils import timezone

    order = make_order("payme")
    Payment.objects.create(order=order, provider="payme", provider_txn_id="p1", amount=order.total)
    assert cancel_unpaid_orders(now=timezone.now() + timedelta(hours=1)) == 0
    Payment.objects.update(status="cancelled")
    assert cancel_unpaid_orders(now=timezone.now() + timedelta(hours=1)) == 1


def test_pay_disabled_provider(make_order, settings):
    settings.PAYMENT_PROVIDERS = ["payme"]
    order = make_order("cash")
    resp = order.client.post(reverse("order-pay", args=[order.number]), {"provider": "click"}, format="json")
    assert resp.json()["error"]["code"] == "provider_disabled"
    resp = order.client.post(reverse("order-pay", args=[order.number]), {"provider": "payme"}, format="json")
    assert resp.status_code == 200 and resp.json()["amount"] == "25000.00"  # naqd: faqat yetkazish narxi
