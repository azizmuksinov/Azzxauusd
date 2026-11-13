"""Tovarlar yorliqlari (sotuvchi kabinetidagi kabi) va qoldiq prognozi."""

import pytest
from django.urls import reverse

from apps.catalog.models import ProductImage
from apps.catalog.tests import factories as f
from apps.orders.models import Order, OrderItem

pytestmark = pytest.mark.django_db


def _sell(variant, qty, status="delivered", n=[0]):  # noqa: B006 — test ichidagi hisoblagich
    from apps.accounts.models import User

    n[0] += 1
    user = User.objects.get_or_create(phone="+998901112233")[0]
    o = Order.objects.create(
        user=user,
        payment_method="cash",
        subtotal=1,
        delivery_fee=0,
        total=1,
        address_snapshot={},
        recipient_name="A",
        recipient_phone="+998901112233",
        delivery_provider="own",
        delivery_vehicle="standard",
        delivery_eta_min=1,
        delivery_eta_max=2,
        idempotency_key=f"ins-{n[0]}",
        status=status,
    )
    OrderItem.objects.create(
        order=o,
        variant=variant,
        product_name={"uz": "x"},
        sku=variant.sku,
        qty=qty,
        unit_price=1,
        line_total=1,
        warranty_months=12,
        vat_percent=12,
    )


def _full(p):
    ProductImage.objects.create(product=p, external_url="https://x/1.jpg")
    p.description = {"uz": "Tavsif"}
    p.save()
    p.variants.update(weight_kg=5, length_cm=10, width_cm=10, height_cm=10)


def test_tabs_counts_and_forecast(staff_client):
    cat = f.category()
    ok = f.product(cat, name={"uz": "Yaxshi"})
    _full(ok)
    f.stock(ok.variants.get(), 100)
    _sell(ok.variants.get(), 60)  # 30 kunda 60 → kuniga 2 → 100 dona ~50 kunga
    _sell(ok.variants.get(), 99, status="cancelled")  # hisoblanmaydi

    fast = f.product(cat, name={"uz": "Tez sotiladi"})
    _full(fast)
    f.stock(fast.variants.get(), 20)
    _sell(fast.variants.get(), 90)  # kuniga 3 → ~7 kun → "Tugayapti"

    out = f.product(cat, name={"uz": "Tugagan"})  # rasm/tavsif/o'lcham yo'q
    draft = f.product(cat, name={"uz": "Qoralama"}, status="draft")
    _full(draft)
    f.product(cat, name={"uz": "Arxiv"}, status="archived")

    c = staff_client("content_manager")
    tabs = {t["key"]: t["count"] for t in c.get(reverse("admin-product-tabs")).json()}
    assert tabs == {
        "all": 4,
        "selling": 2,
        "low": 1,
        "out": 1,
        "not_selling": 1,
        "needs_fix": 1,
        "no_dims": 1,
        "archived": 1,
    }

    rows = c.get(reverse("admin-product-list"), {"tab": "low"}).json()["results"]
    assert [r["name"]["uz"] for r in rows] == ["Tez sotiladi"]
    assert rows[0]["health"] == {
        "available": 20,
        "sales_30d": 90,
        "days_left": 7,
        "flags": [],
        "tabs": ["all", "low", "selling"],
    }
    h = c.get(reverse("admin-product-detail", args=[ok.id])).json()["health"]
    assert (h["sales_30d"], h["days_left"]) == (60, 50)
    fix = c.get(reverse("admin-product-list"), {"tab": "needs_fix"}).json()["results"]
    assert [r["id"] for r in fix] == [out.id]
    assert fix[0]["health"]["flags"] == ["no_image", "no_description", "no_dims"]
