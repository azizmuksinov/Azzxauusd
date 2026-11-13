from decimal import Decimal

import pytest
from django.urls import reverse

from apps.backoffice import services
from apps.backoffice.models import CashAccount, PurchaseReceipt, Supplier
from apps.catalog.models import Product
from apps.catalog.tests import factories as f
from apps.core.exceptions import ApiError
from apps.inventory.models import SerialUnit, Stock, StockMovement

pytestmark = pytest.mark.django_db


@pytest.fixture
def wh(staff_client):
    return staff_client("warehouse")


@pytest.fixture
def setup():
    supplier = Supplier.objects.create(name="Texno Import MChJ", inn="123456789")
    main, second = f.warehouse("main"), f.warehouse("second")
    variant = f.product(f.category(), price="1000000").variants.first()
    variant.cost_price = None
    variant.save()
    return supplier, main, second, variant


def create_receipt(client, supplier, warehouse, lines):
    resp = client.post(
        reverse("bo-receipt-list"),
        {"supplier": supplier.id, "warehouse": warehouse.id, "supplier_doc_number": "YX-1", "lines": lines},
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


def test_receipt_post_updates_stock_and_average_cost(wh, setup):
    supplier, main, _, v = setup
    r1 = create_receipt(wh, supplier, main, [{"variant": v.id, "qty": 10, "unit_cost": "700000"}])
    assert r1["number"].startswith("KR-") and r1["status"] == "draft" and r1["total"] == "7000000.00"
    assert Stock.objects.filter(variant=v).count() == 0  # qoralama qoldiqqa ta'sir qilmaydi

    resp = wh.post(reverse("bo-receipt-post", args=[r1["id"]]))
    assert resp.status_code == 200 and resp.json()["status"] == "posted"
    v.refresh_from_db()
    assert Stock.objects.get(variant=v, warehouse=main).on_hand == 10 and v.cost_price == Decimal("700000.00")

    r2 = create_receipt(wh, supplier, main, [{"variant": v.id, "qty": 5, "unit_cost": "820000"}])
    wh.post(reverse("bo-receipt-post", args=[r2["id"]]))
    v.refresh_from_db()
    assert v.cost_price == Decimal("740000.00")  # (10*700k + 5*820k) / 15
    assert StockMovement.objects.filter(ref_type="purchase_receipt").count() == 2

    # o'tkazilgan hujjat — qulf
    assert wh.post(reverse("bo-receipt-post", args=[r1["id"]])).json()["error"]["code"] == "not_draft"
    assert (
        wh.patch(reverse("bo-receipt-detail", args=[r1["id"]]), {"comment": "x"}, format="json").status_code
        == 400
    )
    assert wh.delete(reverse("bo-receipt-detail", args=[r1["id"]])).status_code == 405

    balance = wh.get(reverse("bo-supplier-detail", args=[supplier.id])).json()["balance"]
    assert balance == {"received": "11100000.00", "paid": "0.00", "debt": "11100000.00"}


def test_receipt_with_imei(wh, setup):
    supplier, main, _, v = setup
    v.product.serial_tracking = Product.SerialTracking.IMEI
    v.product.save()
    imeis = [f.luhn_imei(f"35999900000{i:03d}") for i in range(2)]
    r = create_receipt(
        wh,
        supplier,
        main,
        [{"variant": v.id, "qty": 2, "unit_cost": "100", "serials": [{"imei1": i} for i in imeis]}],
    )
    assert wh.post(reverse("bo-receipt-post", args=[r["id"]])).status_code == 200
    assert SerialUnit.objects.filter(variant=v, warehouse=main).count() == 2


def test_receipt_invalid_serials_rolls_back(wh, setup):
    supplier, main, _, v = setup
    v.product.serial_tracking = Product.SerialTracking.IMEI
    v.product.save()
    other = f.product(f.category()).variants.first()
    r = create_receipt(
        wh,
        supplier,
        main,
        [
            {"variant": other.id, "qty": 3, "unit_cost": "10"},
            {"variant": v.id, "qty": 1, "unit_cost": "100", "serials": []},
        ],
    )
    resp = wh.post(reverse("bo-receipt-post", args=[r["id"]]))
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "serials_count_mismatch"
    assert not Stock.objects.filter(variant=other).exists()  # birinchi qator ham bekor
    assert PurchaseReceipt.objects.get(pk=r["id"]).status == "draft"


def test_empty_receipt_and_cancel(wh, setup):
    supplier, main, _, v = setup
    r = create_receipt(wh, supplier, main, [])
    assert wh.post(reverse("bo-receipt-post", args=[r["id"]])).json()["error"]["code"] == "empty_document"
    assert wh.post(reverse("bo-receipt-cancel", args=[r["id"]])).json()["status"] == "cancelled"


def test_transfer_with_serials(wh, setup):
    supplier, main, second, v = setup
    v.product.serial_tracking = Product.SerialTracking.SERIAL
    v.product.save()
    r = create_receipt(
        wh,
        supplier,
        main,
        [
            {
                "variant": v.id,
                "qty": 3,
                "unit_cost": "10",
                "serials": [{"serial_number": f"SN{i}"} for i in range(3)],
            }
        ],
    )
    wh.post(reverse("bo-receipt-post", args=[r["id"]]))
    ids = list(SerialUnit.objects.filter(variant=v).order_by("id").values_list("id", flat=True))[:2]

    resp = wh.post(
        reverse("bo-transfer-list"),
        {"source": main.id, "target": second.id, "lines": [{"variant": v.id, "qty": 2, "serial_ids": ids}]},
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    assert wh.post(reverse("bo-transfer-post", args=[resp.json()["id"]])).status_code == 200
    assert Stock.objects.get(variant=v, warehouse=main).on_hand == 1
    assert Stock.objects.get(variant=v, warehouse=second).on_hand == 2
    assert set(SerialUnit.objects.filter(warehouse=second).values_list("id", flat=True)) == set(ids)

    same = wh.post(
        reverse("bo-transfer-list"), {"source": main.id, "target": main.id, "lines": []}, format="json"
    )
    assert same.status_code == 400


def test_transfer_cannot_move_reserved(wh, setup):
    from apps.inventory.services import reserve

    supplier, main, second, v = setup
    f.stock(v, 2, main)
    reserve("order", 1, [(v, 2)])
    resp = wh.post(
        reverse("bo-transfer-list"),
        {"source": main.id, "target": second.id, "lines": [{"variant": v.id, "qty": 1}]},
        format="json",
    )
    assert (
        wh.post(reverse("bo-transfer-post", args=[resp.json()["id"]])).json()["error"]["code"]
        == "out_of_stock"
    )


def test_write_off(wh, setup):
    supplier, main, _, v = setup
    f.stock(v, 5, main)
    resp = wh.post(
        reverse("bo-writeoff-list"),
        {"warehouse": main.id, "reason": "defect", "lines": [{"variant": v.id, "qty": 2}]},
        format="json",
    )
    assert wh.post(reverse("bo-writeoff-post", args=[resp.json()["id"]])).status_code == 200
    assert Stock.objects.get(variant=v).on_hand == 3
    assert StockMovement.objects.filter(reason="write_off").get().delta == -2

    resp = wh.post(
        reverse("bo-writeoff-list"),
        {"warehouse": main.id, "reason": "supplier_return", "lines": [{"variant": v.id, "qty": 1}]},
        format="json",
    )
    assert (
        wh.post(reverse("bo-writeoff-post", args=[resp.json()["id"]])).json()["error"]["code"]
        == "supplier_required"
    )


def test_cash_flow(staff_client, setup):
    supplier, *_ = setup
    fin = staff_client("finance")
    acc = fin.post(
        reverse("bo-cash-account-list"), {"name": "Asosiy kassa", "kind": "cash"}, format="json"
    ).json()
    url = reverse("bo-cash-list")
    assert (
        fin.post(
            url,
            {"account": acc["id"], "direction": "in", "amount": "500000", "category": "courier_cod"},
            format="json",
        ).status_code
        == 201
    )
    resp = fin.post(
        url,
        {"account": acc["id"], "direction": "out", "amount": "900000", "category": "expense"},
        format="json",
    )
    assert resp.json()["error"]["code"] == "insufficient_cash"
    resp = fin.post(
        url,
        {"account": acc["id"], "direction": "out", "amount": "200000", "category": "supplier_payment"},
        format="json",
    )
    assert resp.json()["error"]["code"] == "supplier_required"
    pay = fin.post(
        url,
        {
            "account": acc["id"],
            "direction": "out",
            "amount": "200000",
            "category": "supplier_payment",
            "supplier": supplier.id,
        },
        format="json",
    ).json()
    assert fin.get(reverse("bo-cash-account-detail", args=[acc["id"]])).json()["balance"] == "300000.00"
    assert services.supplier_balance(supplier)["paid"] == Decimal("200000.00")

    rev = fin.post(reverse("bo-cash-reverse", args=[pay["id"]]), {"comment": "xato summa"}, format="json")
    assert rev.status_code == 201 and rev.json()["category"] == "correction"
    assert fin.get(reverse("bo-cash-account-detail", args=[acc["id"]])).json()["balance"] == "500000.00"
    assert services.supplier_balance(supplier)["paid"] == Decimal("0.00")
    assert (
        fin.post(reverse("bo-cash-reverse", args=[pay["id"]]), {"comment": "yana"}, format="json").json()[
            "error"
        ]["code"]
        == "already_reversed"
    )
    assert fin.delete(reverse("bo-cash-detail", args=[pay["id"]])).status_code == 405


def test_bank_account_can_go_negative_check_only_for_cash():
    acc = CashAccount.objects.create(name="Bank", kind="bank")
    services.record_cash(account=acc, direction="out", amount="10", category="expense", user=None)
    assert services.balance(acc) == Decimal("-10.00")


def test_stock_valuation(wh, setup):
    supplier, main, _, v = setup
    r = create_receipt(wh, supplier, main, [{"variant": v.id, "qty": 4, "unit_cost": "250000"}])
    wh.post(reverse("bo-receipt-post", args=[r["id"]]))
    rows = wh.get(reverse("bo-stock-valuation")).json()
    assert rows == [{"warehouse_id": main.id, "warehouse": main.name, "units": 4, "value": "1000000.00"}]


def test_permissions(staff_client, api_client):
    assert api_client.get(reverse("bo-receipt-list")).status_code == 401
    assert staff_client("content_manager").get(reverse("bo-receipt-list")).status_code == 403
    assert staff_client("warehouse").get(reverse("bo-cash-list")).status_code == 403
    assert staff_client("finance").get(reverse("bo-supplier-list")).status_code == 200


def test_supplier_inn_validation(wh):
    assert wh.post(reverse("bo-supplier-list"), {"name": "A", "inn": "12"}, format="json").status_code == 400


def test_post_service_rejects_twice(setup):
    supplier, main, _, v = setup
    r = PurchaseReceipt.objects.create(supplier=supplier, warehouse=main)
    r.lines.create(variant=v, qty=1, unit_cost=1)
    services.post_receipt(r, None)
    with pytest.raises(ApiError):
        services.post_receipt(r, None)
