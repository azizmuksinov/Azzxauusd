import json
from io import BytesIO

import httpx
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from apps.ai_cards import gemini
from apps.ai_cards.excel import detect_columns
from apps.ai_cards.models import CardDraft
from apps.catalog.models import AttributeValue, Product
from apps.catalog.tests import factories as f

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100

CARD = {
    "found": True,
    "confidence": 0.9,
    "brand": "Samsung",
    "model_code": "RB38T676FSA",
    "category_slug": "muzlatkichlar",
    "name_uz": "Samsung RB38 muzlatkichi",
    "name_ru": "Холодильник Samsung RB38",
    "description_uz": "Ikki kamerali muzlatkich.",
    "description_ru": "Двухкамерный холодильник.",
    "warranty_months": 24,
    "weight_kg": 70,
    "dimensions_cm": {"length": 60, "width": 66, "height": 203},
    "is_bulky": True,
    "attributes": {"no_frost": "true", "volume_l": "385 l", "color": "Kumush", "unknown": 1, "energy": "Z"},
    "image_urls": ["https://cdn.example.com/rb38.png", "https://cdn.example.com/broken.jpg", "ftp://x/y.png"],
}


@pytest.fixture(autouse=True)
def gemini_key(settings):
    settings.GEMINI = {
        **settings.GEMINI,
        "API_KEY": "test-key",
        "MODEL": "gemini-test",
        "FALLBACK_MODEL": "",
        "RETRY_DELAYS": [0],
    }


@pytest.fixture
def catalog():
    cat = f.category(slug="muzlatkichlar", name={"uz": "Muzlatkichlar"})
    f.attribute("no_frost", "bool", categories=[cat])
    f.attribute("volume_l", "number", categories=[cat], unit="l")
    f.attribute("color", "enum", categories=[cat], options=[("silver", "Kumush"), ("white", "Oq")])
    f.attribute("energy", "enum", categories=[cat], options=[("a", "A"), ("b", "B")])
    return cat


@pytest.fixture
def fake_gemini():
    """Gemini va rasm serverlarini soxtalash. calls — Gemini'ga yuborilgan so'rovlar."""
    state = {"card": CARD, "calls": [], "status": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "generativelanguage" in url and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "models/gemini-test", "supportedGenerationMethods": ["generateContent"]}
                    ]
                },
            )
        if "generativelanguage" in url:
            state["calls"].append({"headers": dict(request.headers), "body": json.loads(request.content)})
            if state["status"] != 200:
                return httpx.Response(state["status"], json={"error": {"message": "quota"}})
            if (
                state.get("reject_thinking")
                and "thinkingConfig" in state["calls"][-1]["body"]["generationConfig"]
            ):
                return httpx.Response(400, json={"error": {"message": "Thinking level is not supported"}})
            text = "Mana:\n```json\n" + json.dumps(state["card"], ensure_ascii=False) + "\n```"
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": text}]},
                            "groundingMetadata": {
                                "groundingChunks": [
                                    {"web": {"uri": "https://samsung.com/uz/rb38", "title": "samsung.com"}}
                                ]
                            },
                        }
                    ],
                    "modelVersion": "gemini-test-001",
                },
            )
        if "shop.example.uz/product" in url:
            page = (
                '<html><head><meta property="og:image" content="https://cdn.example.com/og.png">'
                '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",'
                '"name":"Samsung RB38T676FSA","brand":{"@type":"Brand","name":"Samsung"},'
                '"image":["https://cdn.example.com/rb38.png"],"sku":"RB38"}</script></head></html>'
            )
            return httpx.Response(200, text=page, headers={"content-type": "text/html; charset=utf-8"})
        if url.endswith("rb38.png"):
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        return httpx.Response(404)

    gemini._transport = httpx.MockTransport(handler)
    yield state
    gemini._transport = None


def xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return SimpleUploadedFile("taminotchi.xlsx", buf.getvalue())


SUPPLIER = [
    ["Ta'minotchi: DEMO Import, narxlar so'mda", None, None],
    ["Артикул", "Наименование товара", "Цена закупки", "Кол-во"],
    ["Холодильники", None, None, None],
    ["A-1", "Холодильник Samsung RB38T676FSA", "6 500 000", 3],
    [None, None, None, None],
    ["A-2", "LG F2V5HS0W", 4100000.0, 2],
]


def upload(client, rows=SUPPLIER):
    return client.post(reverse("ai-batch-list"), {"file": xlsx(rows)}, format="multipart")


def test_detect_columns():
    cols = detect_columns(["Артикул", "Наименование товара", "Цена закупки", "Кол-во"])
    assert cols == {"sku": 0, "name": 1, "price": 2, "qty": 3}


def test_upload_supplier_file(staff_client):
    c = staff_client("content_manager")
    r = upload(c)
    assert r.status_code == 201, r.json()
    b = r.json()
    # "Холодильники" — guruh sarlavhasi (narx va soni yo'q) — tovar emas
    assert b["rows_total"] == 2 and b["columns"]["name"] == "Наименование товара"
    assert b["currency"] == "UZS"
    assert b["counts"]["pending"] == 2
    d = CardDraft.objects.get(supplier_sku="A-1")
    assert (
        d.query == "Холодильник Samsung RB38T676FSA" and str(d.purchase_price) == "6500000.00" and d.qty == 3
    )


def test_bad_file(staff_client):
    c = staff_client("content_manager")
    r = c.post(
        reverse("ai-batch-list"), {"file": SimpleUploadedFile("x.xlsx", b"not excel")}, format="multipart"
    )
    assert r.json()["error"]["code"] == "bad_file"


def test_process_and_normalize(staff_client, catalog, fake_gemini):
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    r = c.post(reverse("ai-batch-process", args=[bid]))
    assert r.status_code == 200, r.json()
    assert r.json()["remaining"] == 1 and r.json()["draft"]["status"] == "ready"

    call = fake_gemini["calls"][0]
    assert call["headers"]["x-goog-api-key"] == "test-key"
    assert call["body"]["tools"] == [{"google_search": {}}]
    prompt = call["body"]["contents"][0]["parts"][0]["text"]
    assert (
        "Холодильник Samsung RB38T676FSA" in prompt
        and "muzlatkichlar" in prompt
        and "silver=Kumush" in prompt
    )

    d = CardDraft.objects.get(supplier_sku="A-1")
    res = d.result
    assert res["category_slug"] == "muzlatkichlar" and res["name"]["uz"] == "Samsung RB38 muzlatkichi"
    # xususiyatlar faqat kategoriyadagilar, qiymatlar tekshirilgan
    assert res["attributes"] == {"no_frost": True, "volume_l": 385.0, "color": "silver"}
    assert any("energy" in w or '"Z"' in w for w in d.warnings)
    # faqat ochiladigan rasm qoldi
    assert res["images"] == ["https://cdn.example.com/rb38.png"]
    assert res["sources"][0]["uri"] == "https://samsung.com/uz/rb38"
    assert d.model_used == "gemini-test-001"


def test_wrong_category_and_not_found(staff_client, catalog, fake_gemini):
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    fake_gemini["card"] = {**CARD, "category_slug": "kosmik-kemalar"}
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    assert d.result["category_slug"] == "" and d.result["attributes"] == {}
    assert any("Kategoriya" in w for w in d.warnings)

    fake_gemini["card"] = {"found": False}
    c.post(reverse("ai-batch-process", args=[bid]))
    assert CardDraft.objects.get(supplier_sku="A-2").status == "not_found"


def test_service_errors_stop_and_keep_rows_pending(staff_client, catalog, fake_gemini):
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    for status, code in [
        (429, "ai_rate_limited"),
        (404, "ai_model_unavailable"),
        (503, "ai_unavailable"),
    ]:
        fake_gemini["status"] = status
        r = c.post(reverse("ai-batch-process", args=[bid]))
        assert r.json()["error"]["code"] == code
    assert CardDraft.objects.filter(status="pending").count() == 2


def test_bad_json_marks_row_failed_and_retry(staff_client, catalog, fake_gemini):
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    fake_gemini["card"] = "not-a-dict"
    r = c.post(reverse("ai-batch-process", args=[bid]))
    assert r.json()["draft"]["status"] == "failed"
    r = c.post(reverse("ai-batch-retry-failed", args=[bid]))
    assert r.json()["counts"]["pending"] == 2 and r.json()["counts"]["failed"] == 0


def test_usd_prices_not_used_as_cost(staff_client, catalog, fake_gemini, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    c = staff_client("content_manager")
    rows = [["Товар", "Кол", "Цена, $"], ["Холодильник Samsung RB38", 3, 410]]
    b = upload(c, rows).json()
    assert b["currency"] == "USD"
    c.post(reverse("ai-batch-process", args=[b["id"]]))
    d = CardDraft.objects.get(batch_id=b["id"])
    r = c.post(reverse("ai-draft-approve", args=[d.id]), {"price": "5990000"}, format="json")
    p = Product.objects.get(slug=r.json()["product_slug"])
    assert p.variants.get().cost_price is None


def test_not_configured(staff_client, settings, catalog):
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    r = c.post(reverse("ai-batch-process", args=[bid]))
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_not_configured"
    assert CardDraft.objects.filter(status="pending").count() == 2


def test_edit_and_approve(staff_client, catalog, fake_gemini, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    url = reverse("ai-draft-detail", args=[d.id])

    r = c.patch(
        url,
        {
            "name": {"uz": "Samsung RB38T676FSA muzlatkichi", "ru": "Холодильник"},
            "attributes": {"color": "white"},
        },
        format="json",
    )
    assert r.status_code == 200, r.json()
    assert r.json()["result"]["name"]["uz"] == "Samsung RB38T676FSA muzlatkichi"
    assert r.json()["result"]["attributes"]["color"] == "white"

    r = c.post(
        reverse("ai-draft-approve", args=[d.id]), {"price": "7990000", "old_price": "7000000"}, format="json"
    )
    assert r.json()["error"]["code"] == "bad_old_price"
    r = c.post(reverse("ai-draft-approve", args=[d.id]), {"price": "7990000"}, format="json")
    assert r.status_code == 200, r.json()
    assert r.json()["status"] == "approved"

    p = Product.objects.get(slug=r.json()["product_slug"])
    assert p.status == "active" and p.brand.name == "Samsung" and p.category.slug == "muzlatkichlar"
    assert p.name["ru"] == "Холодильник" and p.is_bulky and p.warranty_months == 24
    v = p.variants.get()
    assert v.sku == "A-1" and str(v.price) == "7990000.00" and str(v.cost_price) == "6500000.00"
    assert {av.attribute.code for av in AttributeValue.objects.filter(product=p)} == {
        "no_frost",
        "volume_l",
        "color",
    }
    img = p.images.get()
    assert img.file.name.startswith("products/") and img.external_url.endswith("rb38.png")
    # mahsulot saytda ko'rinadi
    assert c.get(reverse("product-detail", args=[p.slug])).status_code == 200

    # ikkinchi marta nashr qilib bo'lmaydi
    r = c.post(reverse("ai-draft-approve", args=[d.id]), {"price": "1"}, format="json")
    assert r.json()["error"]["code"] == "draft_not_ready"


def test_approve_as_draft_and_duplicate_warning(staff_client, catalog, fake_gemini, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    f.product(catalog, model_code="RB38T676FSA")
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    assert "allaqachon bor" in d.warnings[0]
    r = c.post(
        reverse("ai-draft-approve", args=[d.id]),
        {"price": "100", "publish": False, "sku": "MY-SKU"},
        format="json",
    )
    assert Product.objects.get(slug=r.json()["product_slug"]).status == "draft"


def test_reject_and_regenerate(staff_client, catalog, fake_gemini):
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    c.post(reverse("ai-batch-process", args=[bid]))
    d1, d2 = CardDraft.objects.order_by("row_number")
    fake_gemini["card"] = {**CARD, "name_uz": "Yangi nom"}
    r = c.post(reverse("ai-draft-regenerate", args=[d1.id]))
    assert r.json()["result"]["name"]["uz"] == "Yangi nom"
    assert c.post(reverse("ai-draft-reject", args=[d2.id])).json()["status"] == "rejected"
    assert c.post(reverse("ai-draft-regenerate", args=[d2.id])).json()["error"]["code"] == "draft_closed"
    r = c.get(reverse("ai-draft-list"), {"batch": bid, "status": "ready"})
    assert [x["id"] for x in r.json()["results"]] == [d1.id]


def test_permissions(staff_client, auth_client):
    assert auth_client.get(reverse("ai-batch-list")).status_code == 403
    assert staff_client("warehouse").get(reverse("ai-batch-list")).status_code == 403
    assert staff_client("content_manager").get(reverse("ai-batch-list")).status_code == 200


def test_extract_json_variants():
    assert gemini.extract_json('{"a": 1}') == {"a": 1}
    assert gemini.extract_json('matn ```json\n{"a": {"b": 2}}\n``` oxiri') == {"a": {"b": 2}}
    with pytest.raises(gemini.GeminiError):
        gemini.extract_json("JSON yo'q")


def test_ai_check_command(settings, fake_gemini):
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("ai_check", stdout=out)
    assert "flash modellar" in out.getvalue() and "model ishlaydi" not in out.getvalue()
    out = StringIO()
    call_command("ai_check", "--generate", stdout=out)
    assert "model ishlaydi" in out.getvalue()
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    out = StringIO()
    call_command("ai_check", stdout=out)
    assert "sozlanmagan" in out.getvalue()


def test_thinking_level_sent_and_fallback(staff_client, catalog, fake_gemini, settings):
    settings.GEMINI = {**settings.GEMINI, "THINKING_LEVEL": "low"}
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    assert fake_gemini["calls"][0]["body"]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}

    fake_gemini["reject_thinking"] = True
    r = c.post(reverse("ai-batch-process", args=[bid]))
    assert r.json()["draft"]["status"] == "ready"
    assert "thinkingConfig" not in fake_gemini["calls"][-1]["body"]["generationConfig"]


def test_daily_limit(staff_client, catalog, fake_gemini):
    c = staff_client("content_manager")
    r = c.patch(reverse("ai-settings"), {"daily_limit": 1}, format="json")
    assert r.status_code == 200 and r.json()["daily_limit"] == 1 and r.json()["used_today"] == 0
    assert r.json()["provider"] == "gemini" and r.json()["search"] is True
    bid = upload(c).json()["id"]
    r = c.post(reverse("ai-batch-process", args=[bid]))
    assert r.json()["usage"]["used_today"] == 1
    r = c.post(reverse("ai-batch-process", args=[bid]))
    assert r.status_code == 429 and r.json()["error"]["code"] == "ai_daily_limit"
    assert CardDraft.objects.filter(status="pending").count() == 1
    c.patch(reverse("ai-settings"), {"daily_limit": None}, format="json")
    assert c.post(reverse("ai-batch-process", args=[bid])).json()["remaining"] == 0


def test_openai_compatible_provider(staff_client, catalog, settings):
    settings.AI_CARDS = {**settings.AI_CARDS, "PROVIDER": "openai"}
    settings.OPENAI_COMPAT = {
        **settings.OPENAI_COMPAT,
        "BASE_URL": "https://ai.local/v1",
        "API_KEY": "k",
        "MODEL": "qwen",
    }
    seen = {}

    def handler(request):
        if request.url.path.endswith("/chat/completions"):
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = json.loads(request.content)
            text = "```json\n" + json.dumps({**CARD, "image_urls": []}) + "\n```"
            return httpx.Response(200, json={"model": "qwen-x", "choices": [{"message": {"content": text}}]})
        return httpx.Response(404)

    gemini._transport = httpx.MockTransport(handler)
    try:
        c = staff_client("content_manager")
        bid = upload(c).json()["id"]
        r = c.post(reverse("ai-batch-process", args=[bid]))
        assert r.json()["draft"]["status"] == "ready", r.json()
        assert seen["auth"] == "Bearer k" and seen["body"]["model"] == "qwen"
        prompt = seen["body"]["messages"][0]["content"]
        assert "Bilimingdan foydalanib" in prompt and "Internetdan" not in prompt
        d = CardDraft.objects.get(supplier_sku="A-1")
        assert d.model_used == "qwen-x" and d.result["name"]["uz"] == "Samsung RB38 muzlatkichi"
        assert c.get(reverse("ai-settings")).json()["search"] is False
    finally:
        gemini._transport = None


def test_busy_model_retries_then_fallback(staff_client, catalog, settings):
    """503 (band): qayta urinish, keyin zaxira model."""
    settings.GEMINI = {**settings.GEMINI, "FALLBACK_MODEL": "gemini-backup", "RETRY_DELAYS": [0]}
    hits = []

    def handler(request):
        url = str(request.url)
        if ":generateContent" in url:
            hits.append(url.split("/models/")[1].split(":")[0])
            if "gemini-test" in url:
                return httpx.Response(503, json={"error": {"message": "high demand"}})
            text = "```json\n" + json.dumps({**CARD, "image_urls": []}) + "\n```"
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": text}]}}], "modelVersion": "backup-1"},
            )
        return httpx.Response(404)

    gemini._transport = httpx.MockTransport(handler)
    try:
        c = staff_client("content_manager")
        bid = upload(c).json()["id"]
        r = c.post(reverse("ai-batch-process", args=[bid]))
        assert r.json()["draft"]["status"] == "ready", r.json()
        assert hits == ["gemini-test", "gemini-test", "gemini-backup"]
        assert CardDraft.objects.get(supplier_sku="A-1").model_used == "backup-1"
    finally:
        gemini._transport = None


def test_import_from_url(staff_client, catalog, fake_gemini):
    from apps.ai_cards.page_hints import parse

    c = staff_client("content_manager")
    fake_gemini["card"] = {**CARD, "image_urls": []}
    r = c.post(reverse("ai-draft-from-url"), {"url": "https://shop.example.uz/product/123"}, format="json")
    assert r.status_code == 201, r.json()
    d = r.json()
    assert d["status"] == "ready" and d["raw"]["hints"]["brand"] == "Samsung"
    # sahifa rasmi (JSON-LD) kartochkaga qo'shildi
    assert d["result"]["images"] == ["https://cdn.example.com/rb38.png"]
    body = fake_gemini["calls"][-1]["body"]
    assert {"url_context": {}} in body["tools"] and {"google_search": {}} in body["tools"]
    prompt = body["contents"][0]["parts"][0]["text"]
    assert "https://shop.example.uz/product/123" in prompt and "so'zma-so'z ko'chirma" in prompt

    assert c.post(reverse("ai-draft-from-url"), {"url": "ftp://x"}, format="json").status_code == 400
    # og teglari zaxira sifatida
    hints = parse(
        '<meta content="Mahsulot" property="og:title"><meta property="og:image" content="https://x/y.jpg">'
    )
    assert hints == {"name": "Mahsulot", "images": ["https://x/y.jpg"]}


def test_fill_images_command(catalog, fake_gemini, settings, tmp_path):
    from io import StringIO

    from django.core.management import call_command

    settings.MEDIA_ROOT = str(tmp_path)
    p = f.product(catalog, name={"uz": "Samsung RB38 muzlatkichi"})
    out = StringIO()
    call_command("ai_fill_images", stdout=out)
    assert p.images.count() == 1 and "1 ta tovarga" in out.getvalue()
    call_command("ai_fill_images", stdout=StringIO())  # rasmi bor — qayta so'ralmaydi
    assert p.images.count() == 1


def test_find_images_endpoint(staff_client, catalog, fake_gemini, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    p = f.product(catalog)
    c = staff_client("content_manager")
    r = c.post(reverse("ai-find-images", args=[p.id]))
    assert r.status_code == 200 and r.json()["images"] == 1
    assert c.post(reverse("ai-find-images", args=[p.id])).json()["error"]["code"] == "has_images"
    p2 = f.product(catalog)
    fake_gemini["status"] = 429
    r = c.post(reverse("ai-find-images", args=[p2.id]))
    assert r.status_code == 429 and r.json()["error"]["code"] == "ai_rate_limited"
