import threading
from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.tests import factories as f
from apps.core.exceptions import ApiError
from apps.inventory import services
from apps.inventory.imei import is_valid_imei
from apps.inventory.models import Reservation, SerialUnit, Stock, StockMovement
from apps.inventory.services import OutOfStock, SerialInput

pytestmark = pytest.mark.django_db


@pytest.fixture
def variant():
    return f.product(f.category()).variants.first()


@pytest.fixture
def phone_variant():
    return f.product(f.category(), serial_tracking=Product.SerialTracking.IMEI).variants.first()


def test_imei_luhn():
    assert is_valid_imei("490154203237518")
    assert not is_valid_imei("490154203237519")
    assert not is_valid_imei("49015420323751")


def test_receive_and_movement(variant):
    wh = f.warehouse()
    stock = services.receive(wh, variant, 5, ref=("receipt", "YX-1"))
    services.receive(wh, variant, 3)
    stock.refresh_from_db()
    assert stock.on_hand == 8 and stock.available == 8
    moves = list(
        StockMovement.objects.filter(variant=variant).order_by("id").values_list("delta", "on_hand_after")
    )
    assert moves == [(5, 5), (3, 8)]


def test_receive_serials(phone_variant):
    wh = f.warehouse()
    imeis = [f.luhn_imei(f"35000000000{i:03d}") for i in range(2)]
    services.receive(wh, phone_variant, 2, serials=[SerialInput(imei1=i) for i in imeis])
    assert SerialUnit.objects.filter(variant=phone_variant, status="in_stock").count() == 2


@pytest.mark.parametrize(
    ("serials", "code"),
    [
        ([], "serials_count_mismatch"),
        ([SerialInput(serial_number="SN1"), SerialInput(serial_number="SN2")], "imei_required"),
        ([SerialInput(imei1="350000000000001"), SerialInput(imei1="350000000000002")], "imei_invalid"),
    ],
)
def test_receive_serial_validation(phone_variant, serials, code):
    with pytest.raises(ApiError) as exc:
        services.receive(f.warehouse(), phone_variant, 2, serials=serials)
    assert exc.value.error_code == code
    assert not Stock.objects.filter(variant=phone_variant, on_hand__gt=0).exists()


def test_receive_duplicate_imei(phone_variant):
    imei = f.luhn_imei("35000000000999")
    services.receive(f.warehouse(), phone_variant, 1, serials=[SerialInput(imei1=imei)])
    with pytest.raises(ApiError) as exc:
        services.receive(f.warehouse(), phone_variant, 1, serials=[SerialInput(imei1=imei)])
    assert exc.value.error_code == "serial_duplicate"
    with pytest.raises(ApiError):
        services.receive(f.warehouse(), phone_variant, 2, serials=[SerialInput(imei1=imei)] * 2)


def test_non_serial_product_rejects_serials(variant):
    with pytest.raises(ApiError):
        services.receive(f.warehouse(), variant, 1, serials=[SerialInput(serial_number="X")])


def test_reserve_commit(variant):
    wh = f.warehouse()
    services.receive(wh, variant, 5)
    services.reserve("order", 1, [(variant, 3)])
    stock = Stock.objects.get(variant=variant)
    assert (stock.on_hand, stock.reserved) == (5, 3)
    assert services.available_by_variant([variant.id]) == {variant.id: 2}

    assert services.commit("order", 1) == 3
    stock.refresh_from_db()
    assert (stock.on_hand, stock.reserved) == (2, 0)
    assert StockMovement.objects.filter(reason="sale", ref_id="1").get().delta == -3
    assert services.commit("order", 1) == 0  # qayta commit — hech narsa qilmaydi


def test_reserve_release(variant):
    services.receive(f.warehouse(), variant, 2)
    services.reserve("order", 7, [(variant, 2)])
    assert services.release("order", 7) == 2
    assert Stock.objects.get(variant=variant).reserved == 0
    assert Reservation.objects.get(ref_id="7").status == "released"


def test_reserve_splits_across_warehouses(variant):
    a, b = f.warehouse("a"), f.warehouse("b")
    services.receive(a, variant, 2)
    services.receive(b, variant, 3)
    res = services.reserve("order", 1, [(variant, 4)])
    assert sorted((r.warehouse.code, r.qty) for r in res) == [("a", 1), ("b", 3)]


def test_reserve_all_or_nothing(variant):
    other = f.product(f.category()).variants.first()
    services.receive(f.warehouse(), variant, 5)
    services.receive(f.warehouse(), other, 1)
    with pytest.raises(OutOfStock) as exc:
        services.reserve("order", 1, [(variant, 2), (other, 2)])
    assert exc.value.extra["items"] == [
        {"variant_id": other.id, "sku": other.sku, "requested": 2, "missing": 1}
    ]
    assert Stock.objects.get(variant=variant).reserved == 0
    assert not Reservation.objects.exists()


def test_reserve_ignores_unsellable_warehouse(variant):
    services.receive(f.warehouse("brak", is_sellable=False), variant, 5)
    with pytest.raises(OutOfStock):
        services.reserve("order", 1, [(variant, 1)])


def test_adjust(variant):
    wh = f.warehouse()
    services.receive(wh, variant, 5)
    services.reserve("order", 1, [(variant, 3)])
    with pytest.raises(ApiError) as exc:
        services.adjust(wh, variant, 2, comment="inventarizatsiya")
    assert exc.value.error_code == "below_reserved"
    services.adjust(wh, variant, 4, comment="inventarizatsiya")
    assert StockMovement.objects.filter(reason="adjustment").get().delta == -1
    with pytest.raises(ApiError):
        services.adjust(wh, variant, 4, comment="")


def test_release_expired(variant):
    services.receive(f.warehouse(), variant, 3)
    services.reserve("order", 1, [(variant, 1)], expires_at=timezone.now() - timedelta(minutes=1))
    services.reserve("order", 2, [(variant, 1)], expires_at=timezone.now() + timedelta(minutes=10))
    assert services.release_expired() == 1
    assert Stock.objects.get(variant=variant).reserved == 1


def test_db_constraint_reserved_le_on_hand(variant):
    stock = services.receive(f.warehouse(), variant, 1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Stock.objects.filter(pk=stock.pk).update(reserved=2)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_reserve_last_item():
    """Oxirgi dona uchun bir vaqtda 5 ta buyurtma: faqat bittasi muvaffaqiyatli bo'ladi."""
    v = f.product(f.category()).variants.first()
    services.receive(f.warehouse(), v, 1)
    results = []
    barrier = threading.Barrier(5)

    def worker(n):
        barrier.wait()
        try:
            services.reserve("order", n, [(v, 1)])
            results.append("ok")
        except OutOfStock:
            results.append("out")
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["ok", "out", "out", "out", "out"]
    assert Stock.objects.get(variant=v).reserved == 1
