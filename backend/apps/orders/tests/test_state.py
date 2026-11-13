import pytest

from apps.orders.models import OrderStatus
from apps.orders.state import TRANSITIONS, can_transition

S = OrderStatus


def test_every_status_has_rules():
    assert set(TRANSITIONS) == set(S.values)


@pytest.mark.parametrize(
    ("a", "b", "ok"),
    [
        (S.CREATED, S.PAID, True),
        (S.CREATED, S.PICKING, False),  # to'lov/tasdiqsiz yig'ilmaydi
        (S.PACKED, S.CANCELLED, True),
        (S.HANDED_TO_COURIER, S.CANCELLED, False),
        (S.OUT_FOR_DELIVERY, S.DELIVERED, True),
        (S.REFUSED_AT_DOOR, S.RETURNED, True),
        (S.DELIVERED, S.RETURNED, False),  # yetkazilgandan keyin — qaytarish arizasi orqali
        (S.CANCELLED, S.CREATED, False),
    ],
)
def test_transitions(a, b, ok):
    assert can_transition(a, b) is ok


@pytest.mark.django_db
def test_handover_commits_stock(client_with_cart, phone_variant, address, tashkent_zone):
    import uuid

    from django.urls import reverse

    from apps.inventory.models import Stock
    from apps.orders.models import Order
    from apps.orders.state import transition

    c = client_with_cart((phone_variant, 2))
    qid = c.post(reverse("checkout-delivery"), {"address_id": address.id}, format="json").json()["quote_id"]
    c.post(
        reverse("orders"),
        {"address_id": address.id, "quote_id": qid, "payment_method": "cash"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    order = Order.objects.get()
    for s in [S.COD_CONFIRMED, S.PICKING, S.PACKED, S.HANDED_TO_COURIER]:
        order = transition(order, s, actor_type="staff")
    stock = Stock.objects.get(variant=phone_variant)
    assert (stock.on_hand, stock.reserved) == (3, 0)
    assert [h.to_status for h in order.history.all()] == [
        "created",
        "cod_confirmed",
        "picking",
        "packed",
        "handed_to_courier",
    ]
