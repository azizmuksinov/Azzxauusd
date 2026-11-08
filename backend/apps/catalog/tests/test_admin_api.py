from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from apps.catalog.models import PriceHistory, Product, ProductVariant
from apps.catalog.tests import factories as f

pytestmark = pytest.mark.django_db


@pytest.fixture
def cm(staff_client):
    return staff_client("content_manager")


def test_permissions(api_client, auth_client, staff_client, cm):
    url = reverse("admin-product-list")
    assert api_client.get(url).status_code == 401
    assert auth_client.get(url).status_code == 403  # oddiy xaridor
    assert staff_client("courier").get(url).status_code == 403
    assert cm.get(url).status_code == 200
    assert staff_client("admin").get(url).status_code == 200


def test_category_and_attribute_crud(cm):
    resp = cm.post(
        reverse("admin-attribute-list"),
        {
            "code": "color",
            "name": {"uz": "Rang", "ru": "Цвет"},
            "data_type": "enum",
            "is_filterable": True,
            "options": [{"code": "black", "value": {"uz": "Qora"}}, {"code": "white", "value": {"uz": "Oq"}}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    attr_id = resp.json()["id"]
    assert [o["code"] for o in resp.json()["options"]] == ["black", "white"]

    resp = cm.post(
        reverse("admin-category-list"),
        {
            "slug": "tv",
            "name": {"uz": "Televizorlar"},
            "attribute_ids": [attr_id],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["attribute_ids"] == [attr_id]

    resp = cm.post(reverse("admin-category-list"), {"slug": "x", "name": {"ru": "только рус"}}, format="json")
    assert resp.status_code == 400 and "name" in resp.json()["error"]["fields"]
    resp = cm.post(
        reverse("admin-category-list"), {"slug": "y", "name": {"uz": "a", "en": "b"}}, format="json"
    )
    assert resp.status_code == 400


def test_category_cycle_rejected(cm):
    root = f.category("root")
    child = f.category("child", parent=root)
    resp = cm.patch(reverse("admin-category-detail", args=[root.id]), {"parent": child.id}, format="json")
    assert resp.status_code == 400


def test_options_validation(cm):
    resp = cm.post(
        reverse("admin-attribute-list"),
        {
            "code": "size",
            "name": {"uz": "O'lcham"},
            "data_type": "number",
            "options": [{"code": "a", "value": {"uz": "A"}}],
        },
        format="json",
    )
    assert resp.status_code == 400


def test_product_with_attributes_and_activation(cm):
    cat = f.category("tv")
    size = f.attribute("screen_size", "number", categories=[cat])
    smart = f.attribute("smart_tv", "bool", categories=[cat])
    payload = {
        "category": cat.id,
        "slug": "tv-1",
        "name": {"uz": "Televizor"},
        "status": "active",
        "attributes": [{"code": "screen_size", "value": 55}, {"code": "smart_tv", "value": True}],
    }
    resp = cm.post(reverse("admin-product-list"), payload, format="json")
    assert resp.status_code == 400 and "mxik_code" in resp.json()["error"]["fields"]

    resp = cm.post(
        reverse("admin-product-list"), {**payload, "mxik_code": "08471001001000000"}, format="json"
    )
    assert resp.status_code == 201, resp.json()
    product = Product.objects.get(slug="tv-1")
    assert product.attribute_values.get(attribute=size).value_number == 55
    assert product.attribute_values.get(attribute=smart).value_bool is True

    # qiymatni o'chirish (null)
    resp = cm.patch(
        reverse("admin-product-detail", args=[product.id]),
        {"attributes": [{"code": "smart_tv", "value": None}]},
        format="json",
    )
    assert resp.status_code == 200
    assert not product.attribute_values.filter(attribute=smart).exists()

    resp = cm.patch(
        reverse("admin-product-detail", args=[product.id]),
        {"attributes": [{"code": "screen_size", "value": "katta"}]},
        format="json",
    )
    assert resp.status_code == 400


def test_product_delete_archives(cm):
    p = f.product(f.category())
    assert cm.delete(reverse("admin-product-detail", args=[p.id])).status_code == 204
    p.refresh_from_db()
    assert p.status == "archived"


def test_variant_create_and_price_via_endpoint_only(cm):
    p = f.product(f.category(), variants=0)
    resp = cm.post(
        reverse("admin-variant-list"), {"product": p.id, "sku": "NEW-1", "price": "1000.00"}, format="json"
    )
    assert resp.status_code == 201, resp.json()
    vid = resp.json()["id"]
    assert PriceHistory.objects.filter(variant_id=vid).count() == 1

    resp = cm.patch(reverse("admin-variant-detail", args=[vid]), {"price": "900"}, format="json")
    assert resp.status_code == 400  # narx faqat /price orqali

    resp = cm.patch(
        reverse("admin-variant-price", args=[vid]), {"price": "900", "old_price": "1000"}, format="json"
    )
    assert resp.status_code == 200, resp.json()
    assert resp.json()["price"] == "900.00"
    hist = cm.get(reverse("admin-variant-price-history", args=[vid])).json()
    assert [h["price"] for h in hist] == ["900.00", "1000.00"]

    resp = cm.patch(
        reverse("admin-variant-price", args=[vid]), {"price": "900", "old_price": "800"}, format="json"
    )
    assert resp.status_code == 400


def test_same_price_not_logged_twice(cm):
    v = f.product(f.category()).variants.first()
    url = reverse("admin-variant-price", args=[v.id])
    cm.patch(url, {"price": "500"}, format="json")
    cm.patch(url, {"price": "500"}, format="json")
    assert v.price_history.count() == 1


def test_image_upload_external_url(cm):
    p = f.product(f.category())
    resp = cm.post(
        reverse("admin-product-image-list"), {"product": p.id, "external_url": "https://cdn.example.uz/a.jpg"}
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["url"] == "https://cdn.example.uz/a.jpg"
    assert cm.post(reverse("admin-product-image-list"), {"product": p.id}).status_code == 400


# --- Excel import ---
def xlsx(rows: list[list]) -> SimpleUploadedFile:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return SimpleUploadedFile("t.xlsx", buf.getvalue())


HEADER = ["sku", "name_uz", "name_ru", "category", "brand", "price", "old_price", "cost_price", "status"]


def test_import_template(cm):
    resp = cm.get(reverse("admin-import-template"))
    assert resp.status_code == 200
    ws = load_workbook(BytesIO(resp.content)).active
    assert [c.value for c in ws[1]][:2] == ["sku", "name_uz"]


def test_import_create_update_and_errors(cm, django_capture_on_commit_callbacks):
    cat = f.category("smartfonlar")
    f.brand("Samsung")
    existing = f.product(cat).variants.first()
    file = xlsx(
        [
            HEADER,
            [
                "A55",
                "Samsung Galaxy A55",
                "Самсунг",
                "smartfonlar",
                "samsung",
                "4 990 000",
                5490000,
                4200000,
                "active",
            ],
            [existing.sku, None, None, None, None, 777000, None, None, None],
            ["BAD1", "Nomi", None, "yoq-kategoriya", None, 100, None, None, None],
            ["BAD2", "Nomi", None, "smartfonlar", None, "narx", None, None, None],
            ["BAD3", "Nomi", None, "smartfonlar", None, 100, 50, None, None],
            [None, None, None, None, None, None, None, None, None],
        ]
    )
    with django_capture_on_commit_callbacks(execute=True):
        resp = cm.post(reverse("admin-import-list"), {"file": file}, format="multipart")
    assert resp.status_code == 202, resp.json()
    job = cm.get(reverse("admin-import-detail", args=[resp.json()["id"]])).json()
    assert job["status"] == "done"
    assert (job["rows_total"], job["rows_ok"], job["rows_failed"]) == (5, 2, 3)
    assert [e["sku"] for e in job["errors"]] == ["BAD1", "BAD2", "BAD3"]

    v = ProductVariant.objects.get(sku="A55")
    assert v.price == 4990000 and v.old_price == 5490000 and v.product.status == "active"
    assert v.product.name == {"uz": "Samsung Galaxy A55", "ru": "Самсунг"}
    existing.refresh_from_db()
    assert existing.price == 777000
    assert existing.price_history.first().source == "excel"


def test_import_dry_run_writes_nothing(cm, django_capture_on_commit_callbacks):
    f.category("smartfonlar")
    file = xlsx([HEADER, ["A55", "Samsung Galaxy A55", None, "smartfonlar", None, 100, None, None, None]])
    with django_capture_on_commit_callbacks(execute=True):
        resp = cm.post(reverse("admin-import-list"), {"file": file, "dry_run": True}, format="multipart")
    job = cm.get(reverse("admin-import-detail", args=[resp.json()["id"]])).json()
    assert job["rows_ok"] == 1
    assert not ProductVariant.objects.filter(sku="A55").exists()


def test_import_rejects_non_xlsx(cm):
    resp = cm.post(
        reverse("admin-import-list"), {"file": SimpleUploadedFile("a.csv", b"x")}, format="multipart"
    )
    assert resp.status_code == 400


def test_import_bad_header(cm, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        resp = cm.post(
            reverse("admin-import-list"), {"file": xlsx([["foo", "bar"], [1, 2]])}, format="multipart"
        )
    job = cm.get(reverse("admin-import-detail", args=[resp.json()["id"]])).json()
    assert job["rows_failed"] == 1 and "sku" in job["errors"][0]["error"]


def test_product_slug_auto_and_video(staff_client):
    from django.urls import reverse

    from apps.catalog.tests import factories as f

    c = staff_client("content_manager")
    cat = f.category()
    r = c.post(
        reverse("admin-product-list"),
        {"category": cat.id, "name": {"uz": "Yangi televizor"}, "video_url": "https://youtu.be/abc"},
        format="json",
    )
    assert r.status_code == 201, r.json()
    assert r.json()["slug"] == "yangi-televizor" and r.json()["video_url"] == "https://youtu.be/abc"
    assert r.json()["image"] == "" and r.json()["stock"] == {}
