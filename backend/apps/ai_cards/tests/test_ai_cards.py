import json
import struct
from io import BytesIO

import httpx
import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from apps.ai_cards import gemini
from apps.ai_cards.excel import detect_columns
from apps.ai_cards.models import CardDraft
from apps.catalog.models import AttributeValue, Product
from apps.catalog.tests import factories as f

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 600, 600) + b"0" * 100
SMALL_PNG = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 64, 64) + b"0" * 100

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
def no_real_search(monkeypatch):
    """Testlarda haqiqiy internet qidiruvi yo'q; kerak bo'lsa natija qo'lda beriladi."""
    from apps.ai_cards import research

    state = {"results": [], "images": [], "real_image_search": research.image_search}
    monkeypatch.setattr(research, "web_search", lambda q, max_results=8: list(state["results"]))
    monkeypatch.setattr(research, "image_search", lambda q, *a, **kw: list(state["images"]))
    return state


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
        if url.startswith("https://r.jina.ai/"):
            return httpx.Response(200, text="Samsung RB38T676FSA: No Frost, 385 l, inverter kompressor.")
        if "shop.example.uz/product" in url:
            page = (
                '<html><head><meta property="og:image" content="https://cdn.example.com/og.png">'
                '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",'
                '"name":"Samsung RB38T676FSA","brand":{"@type":"Brand","name":"Samsung"},'
                '"image":["https://cdn.example.com/rb38.png"],"sku":"RB38"}</script></head></html>'
            )
            return httpx.Response(200, text=page, headers={"content-type": "text/html; charset=utf-8"})
        if url.endswith("thumb.png"):
            return httpx.Response(200, content=SMALL_PNG, headers={"content-type": "image/png"})
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
    assert d.model_used == "gemini: gemini-test-001"


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
        cache.clear()  # 429 dan keyin xizmat 1 daqiqa navbatdan chiqadi
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
    assert "gemini (Google Gemini) — ulangan" in out.getvalue() and "ishlaydi" not in out.getvalue()
    out = StringIO()
    call_command("ai_check", "--generate", stdout=out)
    assert "gemini ishlaydi" in out.getvalue()
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    out = StringIO()
    call_command("ai_check", stdout=out)
    assert "hech bir xizmat ulanmagan" in out.getvalue()


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
    """DeepSeek (OpenAI-mos): Gemini ulanmagan bo'lsa — keyingi ulangan xizmat."""
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    settings.AI_PROVIDER_CONFIG = {
        **settings.AI_PROVIDER_CONFIG,
        "deepseek": {
            **settings.AI_PROVIDER_CONFIG["deepseek"],
            "base_url": "https://ai.local",
            "api_key": "k",
            "model": "qwen",
        },
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
        assert d.model_used == "deepseek: qwen-x" and d.result["name"]["uz"] == "Samsung RB38 muzlatkichi"
        s = c.get(reverse("ai-settings")).json()
        assert s["provider"] == "deepseek" and s["search"] is False
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
        assert CardDraft.objects.get(supplier_sku="A-1").model_used == "gemini: backup-1"
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


def test_usd_with_rate_gives_cost(staff_client, catalog, fake_gemini, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    c = staff_client("content_manager")
    b = upload(c, [["Товар", "Кол", "Цена"], ["Холодильник Samsung RB38", 3, 410]]).json()
    assert b["currency"] == ""
    r = c.post(reverse("ai-batch-set-currency", args=[b["id"]]), {"currency": "USD"}, format="json")
    assert r.json()["currency"] == "USD"
    r = c.patch(reverse("ai-settings"), {"usd_rate": "12650"}, format="json")
    assert r.json()["usd_rate"] == "12650.00"
    c.post(reverse("ai-batch-process", args=[b["id"]]))
    d = CardDraft.objects.get(batch_id=b["id"])
    assert c.get(reverse("ai-draft-detail", args=[d.id])).json()["cost_uzs"] == "5186500.00"
    r = c.post(reverse("ai-draft-approve", args=[d.id]), {"price": "6990000"}, format="json")
    p = Product.objects.get(slug=r.json()["product_slug"])
    assert str(p.variants.get().cost_price) == "5186500.00"


def test_fallback_chain_on_quota(staff_client, catalog, settings):
    """Gemini kvotasi tugadi (429) → Perplexity (qidiruv, manbalar); tartibni panelda o'zgartirish."""
    settings.AI_PROVIDER_CONFIG = {
        **settings.AI_PROVIDER_CONFIG,
        "perplexity": {**settings.AI_PROVIDER_CONFIG["perplexity"], "api_key": "pk"},
        "yandex": {
            **settings.AI_PROVIDER_CONFIG["yandex"],
            "api_key": "yk",
            "model": "gpt://f1/yandexgpt/latest",
            "headers": {"OpenAI-Project": "f1"},
        },
    }
    calls = []

    def handler(request):
        url = str(request.url)
        if "generativelanguage" in url:
            calls.append("gemini")
            return httpx.Response(429, json={"error": {"message": "quota"}})
        if "perplexity" in url:
            calls.append("perplexity")
            body = json.loads(request.content)
            assert "Internetdan" in body["input"]
            text = "```json\n" + json.dumps({**CARD, "image_urls": []}) + "\n```"
            return httpx.Response(
                200,
                json={
                    "model": "sonar",
                    "output": [
                        {
                            "type": "search_results",
                            "results": [{"title": "Samsung", "url": "https://samsung.com/x"}],
                        },
                        {"type": "message", "content": [{"type": "output_text", "text": text}]},
                    ],
                },
            )
        if "yandex" in url:
            calls.append(("yandex", request.headers.get("openai-project")))
            text = "```json\n" + json.dumps({**CARD, "image_urls": []}) + "\n```"
            return httpx.Response(
                200, json={"model": "yandexgpt", "choices": [{"message": {"content": text}}]}
            )
        return httpx.Response(404)

    gemini._transport = httpx.MockTransport(handler)
    try:
        c = staff_client("content_manager")
        bid = upload(c).json()["id"]
        r = c.post(reverse("ai-batch-process", args=[bid]))
        assert r.json()["draft"]["status"] == "ready"
        assert calls == ["gemini", "perplexity"]
        d = CardDraft.objects.get(supplier_sku="A-1")
        assert (
            d.model_used == "perplexity: sonar" and d.result["sources"][0]["uri"] == "https://samsung.com/x"
        )
        assert any("Zaxira AI" in w for w in d.warnings)

        r = c.patch(reverse("ai-settings"), {"provider_order": ["yandex", "gemini"]}, format="json")
        assert [p["name"] for p in r.json()["providers"]][:2] == ["yandex", "gemini"] and r.json()[
            "provider"
        ] == "yandex"
        calls.clear()
        c.post(reverse("ai-batch-process", args=[bid]))
        assert calls == [("yandex", "f1")]
    finally:
        gemini._transport = None


def test_all_providers_fail(staff_client, catalog, settings, fake_gemini):
    fake_gemini["status"] = 429
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    r = c.post(reverse("ai-batch-process", args=[bid]))
    assert r.status_code == 429 and "Google Gemini" in r.json()["error"]["message"]


def test_free_mode_groq_with_research(staff_client, catalog, settings, fake_gemini, no_real_search):
    """Bepul rejim: qidiruv (ddgs) va sahifani o'qish (JSON-LD + Jina) bizda, Groq faqat kartochka tuzadi."""
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    settings.AI_PROVIDER_CONFIG = {
        **settings.AI_PROVIDER_CONFIG,
        "groq": {
            **settings.AI_PROVIDER_CONFIG["groq"],
            "base_url": "https://api.groq.test/openai/v1",
            "api_key": "gk",
        },
    }
    no_real_search["results"] = [
        {"title": "Samsung RB38", "href": "https://shop.example.uz/product/rb38", "body": "Muzlatkich 385 l"},
        {"title": "Video", "href": "https://www.youtube.com/watch?v=x", "body": ""},
    ]
    base_handler = gemini._transport.handle_request
    seen = {}

    def handler(request):
        if "api.groq.test" in str(request.url):
            seen["prompt"] = json.loads(request.content)["messages"][0]["content"]
            text = "```json\n" + json.dumps({**CARD, "image_urls": []}) + "\n```"
            return httpx.Response(
                200, json={"model": "gpt-oss-120b", "choices": [{"message": {"content": text}}]}
            )
        return base_handler(request)

    gemini._transport = httpx.MockTransport(handler)
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    r = c.post(reverse("ai-batch-process", args=[bid]))
    assert r.json()["draft"]["status"] == "ready", r.json()
    p = seen["prompt"]
    assert "INTERNET MA'LUMOTI" in p and "No Frost, 385 l" in p and "shop.example.uz/product/rb38" in p
    assert "youtube" not in p
    d = CardDraft.objects.get(supplier_sku="A-1")
    assert d.model_used == "groq: gpt-oss-120b"
    assert d.result["sources"][0]["uri"] == "https://shop.example.uz/product/rb38"
    # sahifaning JSON-LD rasmi kartochkaga tushdi (AI rasm bermagan bo'lsa ham)
    assert d.result["images"] == ["https://cdn.example.com/rb38.png"]


def test_find_images_free_without_ai(staff_client, catalog, settings, fake_gemini, no_real_search, tmp_path):
    """Rasm topish: qidiruv + sahifa rasmlari — AI so'rovisiz (kvota sarflanmaydi)."""
    from apps.ai_cards.models import AiCall

    settings.MEDIA_ROOT = str(tmp_path)
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    no_real_search["results"] = [
        {"title": "Samsung", "href": "https://shop.example.uz/product/rb38", "body": ""}
    ]
    p = f.product(catalog)
    c = staff_client("content_manager")
    r = c.post(reverse("ai-find-images", args=[p.id]))
    assert r.status_code == 200 and r.json()["images"] == 1
    assert AiCall.objects.count() == 0 and fake_gemini["calls"] == []


def _free_providers(settings):
    settings.AI_PROVIDER_CONFIG = {
        **settings.AI_PROVIDER_CONFIG,
        "groq": {**settings.AI_PROVIDER_CONFIG["groq"], "base_url": "https://groq.test/v1", "api_key": "g"},
        "cerebras": {
            **settings.AI_PROVIDER_CONFIG["cerebras"],
            "base_url": "https://cerebras.test/v1",
            "api_key": "c",
        },
    }


def test_routes_caps_and_balancing(settings):
    from apps.ai_cards import client
    from apps.ai_cards.models import AiCall
    from apps.core.settings_registry import set_setting

    _free_providers(settings)  # + Gemini (fixture) ulangan
    assert [p.name for p in client.chain("card")][:3] == ["groq", "cerebras", "gemini"]
    assert [p.name for p in client.chain("url")][:3] == ["groq", "cerebras", "gemini"]  # Gemini — zaxira
    # yuklama: groq ko'proq ishlatilgan — cerebras birinchi
    AiCall.objects.bulk_create([AiCall(provider="groq") for _ in range(3)])
    assert [p.name for p in client.chain("card")][:2] == ["cerebras", "groq"]
    # kunlik chegara: groq limiti tugadi — ro'yxatdan chiqadi
    set_setting("ai_provider_caps", "groq=3,cerebras=900")
    assert "groq" not in [p.name for p in client.chain("card")]
    set_setting("ai_provider_caps", "groq=3,cerebras=0,gemini=0")
    assert client.chain("card") == []


def test_all_caps_reached_stops_processing(staff_client, catalog, fake_gemini):
    from apps.core.settings_registry import set_setting

    set_setting("ai_provider_caps", "gemini=0")
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    r = c.post(reverse("ai-batch-process", args=[bid]))
    assert r.status_code == 429 and "limiti tugadi" in r.json()["error"]["message"]
    assert fake_gemini["calls"] == []


def test_learns_from_approved_cards(staff_client, catalog, fake_gemini, settings, tmp_path):
    """Tasdiqlangan (tahrirlangan) kartochka keyingi so'rovlarda uslub namunasi sifatida beriladi."""
    settings.MEDIA_ROOT = str(tmp_path)
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    c.patch(
        reverse("ai-draft-detail", args=[d.id]),
        {"name": {"uz": "Muzlatkich Samsung RB38 — kumushrang", "ru": "Х"}},
        format="json",
    )
    c.post(reverse("ai-draft-approve", args=[d.id]), {"price": "7990000"}, format="json")
    c.post(reverse("ai-batch-process", args=[bid]))
    prompt = fake_gemini["calls"][-1]["body"]["contents"][0]["parts"][0]["text"]
    assert (
        "xodimlari tasdiqlagan kartochkalar namunasi" in prompt
        and "Muzlatkich Samsung RB38 — kumushrang" in prompt
    )


def test_check_endpoint_reports_limits(staff_client, settings):
    _free_providers(settings)

    def handler(request):
        url = str(request.url)
        if "groq.test" in url:
            return httpx.Response(
                200,
                json={"model": "gpt-oss-120b", "choices": [{"message": {"content": "OK"}}]},
                headers={"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "999"},
            )
        if "cerebras.test" in url:
            return httpx.Response(429, json={"error": {"message": "limit"}})
        if "generativelanguage" in url:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "OK"}]}}]})
        return httpx.Response(404)

    gemini._transport = httpx.MockTransport(handler)
    try:
        r = staff_client("content_manager").post(reverse("ai-check"))
        rows = {x["name"]: x for x in r.json()["providers"]}
        assert rows["groq"]["ok"] and rows["groq"]["limits"]["x-ratelimit-limit-requests"] == "1000"
        assert rows["cerebras"]["ok"] is False and "limit" in rows["cerebras"]["error"]
        assert rows["gemini"]["ok"] and rows["openrouter"]["missing"] == "kalit"
        assert r.json()["usage"]["providers"][0]["used_today"] >= 0
    finally:
        gemini._transport = None


def test_category_name_mapped_to_slug(staff_client, catalog, fake_gemini):
    fake_gemini["card"] = {**CARD, "category_slug": "Muzlatkichlar"}
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    assert d.result["category_slug"] == "muzlatkichlar" and d.result["attributes"]


def test_perplexity_responses_api(staff_client, catalog, settings):
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    settings.AI_PROVIDER_CONFIG = {
        **settings.AI_PROVIDER_CONFIG,
        "perplexity": {
            **settings.AI_PROVIDER_CONFIG["perplexity"],
            "base_url": "https://pplx.test",
            "api_key": "pk",
        },
    }
    seen = {}

    def handler(request):
        if request.url.path == "/v1/responses":
            seen["body"] = json.loads(request.content)
            text = "```json\n" + json.dumps({**CARD, "image_urls": []}) + "\n```"
            return httpx.Response(
                200,
                json={
                    "model": "perplexity/sonar",
                    "output": [
                        {
                            "type": "search_results",
                            "results": [{"url": "https://samsung.com/rb38", "title": "Samsung"}],
                        },
                        {"type": "message", "content": [{"type": "output_text", "text": text}]},
                    ],
                },
            )
        return httpx.Response(404)

    gemini._transport = httpx.MockTransport(handler)
    try:
        c = staff_client("content_manager")
        bid = upload(c).json()["id"]
        assert c.post(reverse("ai-batch-process", args=[bid])).json()["draft"]["status"] == "ready"
        assert seen["body"]["tools"] == [{"type": "web_search"}] and "Internetdan" in seen["body"]["input"]
        d = CardDraft.objects.get(supplier_sku="A-1")
        assert d.result["sources"][0]["uri"] == "https://samsung.com/rb38" and d.model_used.startswith(
            "perplexity"
        )
    finally:
        gemini._transport = None


def test_small_thumbnails_rejected(fake_gemini):
    from apps.ai_cards.services import check_images, image_size

    ok, warnings = check_images(["https://cdn.example.com/rb38.png", "https://cdn.example.com/thumb.png"])
    assert ok == ["https://cdn.example.com/rb38.png"] and "64x64" in warnings[0]
    jpeg = b"\xff\xd8\xff\xc0\x00\x11\x08" + struct.pack(">HH", 480, 640) + b"\x00" * 10
    assert image_size(jpeg) == (640, 480)


def test_approve_survives_unwritable_media(staff_client, catalog, fake_gemini, monkeypatch):
    """Media papkasiga yozib bo'lmasa ham nashr o'tadi — rasm tashqi havola bilan qoladi."""
    from django.core.files.storage import FileSystemStorage

    def boom(*a, **kw):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(FileSystemStorage, "_save", boom)
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    r = c.post(reverse("ai-draft-approve", args=[d.id]), {"price": "7990000"}, format="json")
    assert r.status_code == 200, r.json()
    img = Product.objects.get(slug=r.json()["product_slug"]).images.get()
    assert not img.file and img.external_url.endswith("rb38.png")


def test_currency_marks_are_whole_words():
    from apps.ai_cards.excel import detect_currency

    assert detect_currency(["Товар", "Кол", "Цена", "Сумма"]) == ""  # "Сумма" — so'm emas
    assert detect_currency(["Цена, сум"]) == "UZS" and detect_currency(["Narx, soʻm"]) == "UZS"
    assert detect_currency(["narxlar so'mda"]) == "UZS" and detect_currency(["в сумах"]) == "UZS"
    assert detect_currency(["somewhere", "Samsung"]) == ""
    assert detect_currency(["Цена (у.е.)"]) == "USD" and detect_currency(["Price, $"]) == "USD"


def test_rate_limited_provider_skipped_until_reset(settings):
    """Kunlik limiti tugagan xizmat (429) kutish vaqtigacha navbatdan chiqadi — har safar urinilmaydi."""
    from apps.ai_cards import client

    assert client.cooldown_seconds("Please try again in 26m17.66s. Need more") == 1577
    assert client.cooldown_seconds("try again in 712ms") == 60
    assert client.cooldown_seconds("quota") == 60
    _free_providers(settings)
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    hits = {"groq": 0}

    def handler(request):
        if "groq.test" in str(request.url):
            hits["groq"] += 1
            return httpx.Response(
                429, json={"error": {"message": "TPD limit. Please try again in 26m17.6s."}}
            )
        return httpx.Response(
            200, json={"model": "gpt-oss-120b", "choices": [{"message": {"content": "OK"}}]}
        )

    gemini._transport = httpx.MockTransport(handler)
    try:
        assert client.chain("card")[0].name == "groq"
        first = client.generate("x")
        assert first.provider == "cerebras" and first.fallback_notes
        second = client.generate("x")
        assert second.provider == "cerebras" and not second.fallback_notes and hits["groq"] == 1
        assert "groq" not in [p.name for p in client.chain("card")]
    finally:
        gemini._transport = None


def test_export_import_roundtrip(staff_client, catalog, fake_gemini, settings, tmp_path):
    """Zaxira: AI natijalari bilan eksport va tiklash; nashr qilingan — qayta "tekshirish kutilmoqda"."""
    settings.MEDIA_ROOT = str(tmp_path)
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    c.post(reverse("ai-draft-approve", args=[d.id]), {"price": "7990000"}, format="json")
    calls = len(fake_gemini["calls"])

    data = c.get(reverse("ai-batch-export", args=[bid])).json()
    assert data["format"] == "ai-cards/1" and len(data["drafts"]) == 2
    r = c.post(reverse("ai-batch-import"), data, format="json")
    assert r.status_code == 201, r.json()
    new = CardDraft.objects.filter(batch_id=r.json()["id"]).order_by("row_number")
    assert [x.status for x in new] == ["ready", "pending"]
    assert new[0].result == d.result and str(new[0].purchase_price) == "6500000.00"
    assert len(fake_gemini["calls"]) == calls  # AI so'rovi sarflanmadi
    # fayl orqali ham
    f = SimpleUploadedFile("backup.json", json.dumps(data).encode(), content_type="application/json")
    assert c.post(reverse("ai-batch-import"), {"file": f}, format="multipart").status_code == 201
    assert c.post(reverse("ai-batch-import"), {"x": 1}, format="json").json()["error"]["code"] == "bad_backup"


def _png(w, h, salt=b""):
    return (
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"0" * 100 + salt
    )


def test_pick_images_prefers_large_and_mixes_sources():
    """Kattasi oldin, takror fayl tashlanadi, turli saytlardan navbat bilan."""
    from apps.ai_cards.services import pick_images

    files = {
        "https://a.com/1.png": _png(1200, 1200, b"a1"),
        "https://a.com/2.png": _png(1000, 1000, b"a2"),
        "https://a.com/3.png": _png(900, 900, b"a3"),
        "https://b.com/1.png": _png(800, 800, b"b1"),
        "https://b.com/copy.png": _png(1200, 1200, b"a1"),  # a.com/1 bilan bir xil
        "https://c.com/s.png": _png(64, 64, b"c"),
    }

    def handler(request):
        body = files.get(str(request.url))
        return (
            httpx.Response(200, content=body, headers={"content-type": "image/png"})
            if body
            else httpx.Response(404)
        )

    gemini._transport = httpx.MockTransport(handler)
    try:
        picked, warnings = pick_images(list(files), limit=4)
    finally:
        gemini._transport = None
    assert picked == [
        "https://a.com/1.png",
        "https://b.com/1.png",
        "https://a.com/2.png",
        "https://a.com/3.png",
    ]
    assert any("64x64" in w for w in warnings)


def test_image_search_results_used(staff_client, catalog, fake_gemini, no_real_search):
    no_real_search["images"] = ["https://cdn.example.com/rb38.png"]
    fake_gemini["card"] = {**CARD, "image_urls": []}
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    assert CardDraft.objects.get(supplier_sku="A-1").result["images"] == ["https://cdn.example.com/rb38.png"]


def test_full_specs_kept_edited_and_published(staff_client, catalog, fake_gemini, settings, tmp_path):
    """To'liq xususiyatlar: AI'dan normallashadi, tahrirda yo'qolmaydi, nashrda tovar sahifasida ko'rinadi."""
    settings.MEDIA_ROOT = str(tmp_path)
    specs = [
        {
            "group_uz": "Asosiy",
            "group_ru": "Основные",
            "name_uz": "Kompressor",
            "name_ru": "Компрессор",
            "value_uz": "Inverter",
            "value_ru": "Инверторный",
        },
        {"name_uz": "Shovqin", "value": "35 dB"},
        {"name_uz": "Kompressor", "value_uz": "takror"},
        {"name_uz": "", "value_uz": "bo'sh"},
    ]
    fake_gemini["card"] = {**CARD, "specs": specs}
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    assert [s["name"]["uz"] for s in d.result["specs"]] == ["Kompressor", "Shovqin"]
    assert d.result["specs"][1]["value"] == {"uz": "35 dB", "ru": "35 dB"}
    c.patch(reverse("ai-draft-detail", args=[d.id]), {"brand": "Samsung"}, format="json")
    d.refresh_from_db()
    assert len(d.result["specs"]) == 2  # tahrirda saqlanadi
    r = c.post(reverse("ai-draft-approve", args=[d.id]), {"price": "7990000"}, format="json")
    p = Product.objects.get(slug=r.json()["product_slug"])
    groups = c.get(reverse("product-detail", args=[p.slug]), HTTP_ACCEPT_LANGUAGE="ru").json()["attributes"]
    items = {i["name"]: i["value"] for g in groups for i in g["items"]}
    assert items["Компрессор"] == "Инверторный" and items["Shovqin"] == "35 dB"


def test_market_price_from_uz_shops(staff_client, no_real_search, monkeypatch):
    """Bozor narxi: faqat .uz do'konlar; oylik to'lov va aksessuar narxlari tashlanadi; domen — bitta."""
    from apps.ai_cards import market, page_hints

    no_real_search["results"] = [
        {"href": "https://texnomart.uz/p/1", "title": "Premier PRM-G60", "body": "Narxi: 2 990 000 so'm"},
        {
            "href": "https://olcha.uz/p/2",
            "title": "Плита Premier",
            "body": "от 250 000 сум/мес, 3 100 000 сум",
        },
        {
            "href": "https://olcha.uz/p/3",
            "title": "Premier",
            "body": "3 300 000 сум",
        },  # shu do'kon — arzonini
        {"href": "https://mediapark.uz/p/4", "title": "Premier", "body": "rasm yo'q"},  # sahifadan
        {"href": "https://asaxiy.uz/p/5", "title": "Ruchka", "body": "90 000 so'm"},  # aksessuar — tashlanadi
        {"href": "https://ozon.ru/p/6", "title": "Premier", "body": "25 000 ₽"},  # .uz emas
    ]
    monkeypatch.setattr(page_hints, "fetch", lambda url: {"price": 2_850_000.0, "currency": "UZS"})
    r = staff_client("content_manager").post(
        reverse("ai-market-price"), {"query": "Premier PRM-G60-E31B"}, format="json"
    )
    assert r.status_code == 200, r.json()
    d = r.json()
    assert [s["price"] for s in d["sources"]] == [2_850_000, 2_990_000, 3_100_000]
    assert (d["min"], d["median"], d["max"], d["suggested"]) == (2_850_000, 2_990_000, 3_100_000, 2_990_000)
    assert market.prices_in_text("1.299.000 сум в месяц, 12 990 000 so'm") == [12_990_000]


def test_image_search_is_filler_after_page_images():
    """Tovar sahifasi rasmlari oldin; rasm qidiruvi — faqat qolgan joyni to'ldiradi (katta bo'lsa ham)."""
    from apps.ai_cards.services import pick_images

    files = {
        "https://shop.uz/p.png": _png(600, 600, b"p"),
        "https://other.com/huge.png": _png(3000, 3000, b"h"),
    }

    def handler(request):
        body = files.get(str(request.url))
        return (
            httpx.Response(200, content=body, headers={"content-type": "image/png"})
            if body
            else httpx.Response(404)
        )

    gemini._transport = httpx.MockTransport(handler)
    try:
        picked, _ = pick_images(["https://shop.uz/p.png"], extra=["https://other.com/huge.png"])
    finally:
        gemini._transport = None
    assert picked == ["https://shop.uz/p.png", "https://other.com/huge.png"]


def test_image_search_filters_by_model_code(monkeypatch, no_real_search):
    import ddgs

    image_search = no_real_search["real_image_search"]  # haqiqiy funksiya, ddgs esa soxta
    items = [
        {"image": "https://a.com/rb38t676fsa-front.jpg", "width": 1000, "height": 1000, "title": "x"},
        {"image": "https://b.com/1.jpg", "width": 2000, "height": 2000, "title": "Samsung RB38T676FSA/WT"},
        {"image": "https://c.com/galaxy.jpg", "width": 3000, "height": 3000, "title": "Samsung Galaxy S23"},
        {"image": "https://d.com/samsung-logo-RB38T676FSA.png", "width": 900, "height": 900, "title": ""},
        {"image": "https://e.com/rb38t676fsa-small.jpg", "width": 200, "height": 200, "title": ""},
        {
            "image": "https://f.com/x.jpg",
            "width": "",
            "height": "",
            "title": "LG RB38T676FSA",
        },  # o'lcham yo'q
    ]

    class Fake:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def images(self, q, max_results=25):
            return items

    monkeypatch.setattr(ddgs, "DDGS", Fake)
    assert image_search("Samsung RB38T676FSA", "RB38T676FSA") == [
        "https://b.com/1.jpg",
        "https://a.com/rb38t676fsa-front.jpg",
        "https://f.com/x.jpg",
    ]
    assert image_search("Samsung", "") == []


GAS = {"name_uz": "Gaz plitalar", "name_ru": "Газовые плиты", "parent_slug": "maishiy-texnika"}


def test_ai_proposes_new_category_created_on_publish(staff_client, catalog, fake_gemini, settings, tmp_path):
    """Mos kategoriya yo'q — AI yangisini taklif qiladi, nashrda yaratiladi; keyingi tovar o'shanda."""
    from apps.catalog.models import Category

    settings.MEDIA_ROOT = str(tmp_path)
    f.category(slug="maishiy-texnika", name={"uz": "Maishiy texnika"})
    fake_gemini["card"] = {**CARD, "category_slug": None, "new_category": GAS, "attributes": {}}
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    c.post(reverse("ai-batch-process", args=[bid]))
    d1, d2 = CardDraft.objects.order_by("row_number")
    assert d1.result["category_slug"] == "" and d1.result["new_category"] == {
        "name": {"uz": "Gaz plitalar", "ru": "Газовые плиты"},
        "parent_slug": "maishiy-texnika",
    }
    assert "yangi kategoriya" in d1.warnings[0]
    # tahrirda (boshqa maydon) taklif saqlanadi
    c.patch(reverse("ai-draft-detail", args=[d1.id]), {"brand": "Premier"}, format="json")
    d1.refresh_from_db()
    assert d1.result["new_category"]["name"]["uz"] == "Gaz plitalar"

    r = c.post(reverse("ai-draft-approve", args=[d1.id]), {"price": "2950000", "sku": "G-1"}, format="json")
    assert r.status_code == 200, r.json()
    gas = Category.objects.get(slug="gaz-plitalar")
    assert gas.parent.slug == "maishiy-texnika" and gas.name["ru"] == "Газовые плиты"
    assert Product.objects.get(slug=r.json()["product_slug"]).category == gas
    r = c.post(reverse("ai-draft-approve", args=[d2.id]), {"price": "2950000", "sku": "G-2"}, format="json")
    assert Product.objects.get(slug=r.json()["product_slug"]).category == gas
    assert Category.objects.filter(name__uz="Gaz plitalar").count() == 1

    # keyingi kartochkada AI shu nomni taklif qilsa — mavjud kategoriya tanlanadi
    from apps.ai_cards.services import _match_new_category, catalog_context

    assert _match_new_category(GAS, catalog_context()) == ("gaz-plitalar", None)


def test_bulk_categorize_one_ai_call(staff_client, catalog, fake_gemini):
    f.category(slug="maishiy-texnika", name={"uz": "Maishiy texnika"})
    fake_gemini["card"] = {**CARD, "category_slug": None}
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    c.post(reverse("ai-batch-process", args=[bid]))
    d1, d2 = CardDraft.objects.order_by("row_number")
    assert not d1.result["category_slug"] and not d2.result["category_slug"]
    calls = len(fake_gemini["calls"])
    fake_gemini["card"] = {str(d1.id): {"category_slug": "muzlatkichlar"}, str(d2.id): {"new_category": GAS}}
    r = c.post(reverse("ai-batch-categorize", args=[bid]), {}, format="json")
    assert r.status_code == 200, r.json()
    assert {k: r.json()[k] for k in ("total", "matched", "new", "unchanged")} == {
        "total": 2,
        "matched": 1,
        "new": 1,
        "unchanged": 0,
    }
    assert len(fake_gemini["calls"]) == calls + 1  # ikkala kartochka — bitta so'rovda
    d1.refresh_from_db()
    d2.refresh_from_db()
    assert d1.result["category_slug"] == "muzlatkichlar"
    assert d2.result["new_category"]["name"]["uz"] == "Gaz plitalar"


def test_non_json_reply_falls_back_to_next_ai(staff_client, catalog, settings):
    """Model ba'zan JSON o'rniga oddiy matn yozadi — kartochka xato bo'lmaydi, keyingi AI yozadi."""
    _free_providers(settings)
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}

    def handler(request):
        url = str(request.url)
        if "groq.test" in url:
            text = "Kechirasiz, bu sahifani o'qiy olmadim."
        elif "cerebras.test" in url:
            text = "```json\n" + json.dumps(CARD, ensure_ascii=False) + "\n```"
        else:
            return httpx.Response(404)
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": text}}]})

    gemini._transport = httpx.MockTransport(handler)
    try:
        c = staff_client("content_manager")
        bid = upload(c).json()["id"]
        r = c.post(reverse("ai-batch-process", args=[bid]))
    finally:
        gemini._transport = None
    d = CardDraft.objects.get(id=r.json()["draft"]["id"])
    assert d.status == "ready" and d.model_used.startswith("cerebras")
    assert any("JSON emas" in w for w in d.warnings)


def _serve(files):
    """{url: (bytes, content_type)} — soxta rasm serveri."""

    def handler(request):
        item = files.get(str(request.url))
        if not item:
            return httpx.Response(404)
        return httpx.Response(200, content=item[0], headers={"content-type": item[1]})

    return httpx.MockTransport(handler)


def test_image_detected_by_content_not_header():
    """CDN octet-stream yuborsa ham rasm qabul qilinadi; HTML sahifa — rasm emas (sababi bilan)."""
    from apps.ai_cards import images

    gemini._transport = _serve(
        {
            "https://images.uzum.uz/a/t_product_540_high.jpg": (
                b"\xff\xd8\xff\xc0\x00\x11\x08" + struct.pack(">HH", 540, 540) + b"\x00" * 20000,
                "application/octet-stream",
            ),
            "https://images.uzum.uz/a/t_product_high.jpg": (
                b"\xff\xd8\xff\xc0\x00\x11\x08" + struct.pack(">HH", 1200, 1200) + b"\x00" * 30000,
                "binary/octet-stream",
            ),
            "https://shop.uz/img.jpg": (b"<!doctype html><html>blocked</html>", "image/jpeg"),
        }
    )
    try:
        f = images.fetch("https://images.uzum.uz/a/t_product_540_high.jpg")
        assert f.ok and f.ext == "jpg" and f.size == (540, 540)
        best = images.fetch_best("https://images.uzum.uz/a/t_product_540_high.jpg")
        assert best.url == "https://images.uzum.uz/a/t_product_high.jpg" and best.size == (1200, 1200)
        bad = images.fetch("https://shop.uz/img.jpg")
        assert not bad.ok and "rasm emas" in bad.reason
    finally:
        gemini._transport = None
    text = "![Rasm](https://cdn.x.uz/p/1.webp) ![logo](https://cdn.x.uz/logo.png) https://a.uz/b.jpg?w=800"
    assert images.urls_in_text(text) == ["https://cdn.x.uz/p/1.webp", "https://a.uz/b.jpg?w=800"]


def test_autofix_finds_images_and_category(staff_client, catalog, fake_gemini, monkeypatch, no_real_search):
    """Avto-tuzatish: rasmsizga manba sahifasidan rasm topadi, kategoriyasizga AI kategoriya beradi."""
    from apps.ai_cards import page_hints, research

    f.category(slug="maishiy-texnika", name={"uz": "Maishiy texnika"})
    fake_gemini["card"] = {**CARD, "category_slug": None, "image_urls": []}
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    d.result = {**d.result, "sources": [{"uri": "https://shop.uz/rb38", "title": "x"}]}
    d.save()
    assert d.result["images"] == [] and not d.result["category_slug"]

    monkeypatch.setattr(page_hints, "fetch", lambda url: {"images": ["https://cdn.example.com/rb38.png"]})
    monkeypatch.setattr(research, "read_page_full", lambda url, limit=6000: ("", []))
    fake_gemini["card"] = {str(d.id): {"category_slug": "muzlatkichlar"}}
    r = c.post(reverse("ai-draft-autofix", args=[d.id]))
    assert r.status_code == 200, r.json()
    d.refresh_from_db()
    assert d.result["images"] == ["https://cdn.example.com/rb38.png"]
    assert d.result["category_slug"] == "muzlatkichlar"
    assert d.warnings[0].startswith("Avto-tuzatish: rasm: 0 → 1 ta; kategoriya aniqlandi")

    # ommaviy: bir marta urinilgan kartochka qayta olinmaydi (cheksiz aylanish yo'q)
    r = c.post(reverse("ai-batch-autofix", args=[bid])).json()
    assert d.id not in [x["id"] for x in r["fixed"]]


def test_create_proposed_category_button(staff_client, catalog, fake_gemini):
    from apps.catalog.models import Category

    f.category(slug="maishiy-texnika", name={"uz": "Maishiy texnika"})
    fake_gemini["card"] = {**CARD, "category_slug": None, "new_category": GAS, "attributes": {}}
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    r = c.post(reverse("ai-draft-create-category", args=[d.id]))
    assert r.status_code == 200, r.json()
    assert (
        r.json()["result"]["category_slug"] == "gaz-plitalar" and r.json()["result"]["new_category"] is None
    )
    assert Category.objects.get(slug="gaz-plitalar").parent.slug == "maishiy-texnika"
    again = c.post(reverse("ai-draft-create-category", args=[d.id]))
    assert again.json()["error"]["code"] == "no_proposal"


def test_short_model_code_needs_brand(monkeypatch, no_real_search):
    import ddgs

    image_search = no_real_search["real_image_search"]
    items = [
        {"image": "https://a.com/ezviz-h1c.jpg", "width": 1000, "height": 1000, "title": "EZVIZ H1C camera"},
        {"image": "https://b.com/h1c.jpg", "width": 1000, "height": 1000, "title": "Honda H1C part"},
    ]

    class Fake:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def images(self, q, max_results=25):
            return items

    monkeypatch.setattr(ddgs, "DDGS", Fake)
    assert image_search("Ezviz H1c", "H1c", brand="Ezviz") == ["https://a.com/ezviz-h1c.jpg"]
    assert image_search("H1c", "H1c") == []


def test_page_hints_images_from_html_when_no_metadata():
    from apps.ai_cards.page_hints import parse

    photo = "https:\\u002F\\u002Fimages.uzum.uz\\u002Fabc\\u002Ft_product_540_high.jpg"
    page = '<html><script>{"photo":"' + photo + '"}</script>'
    page += '<img src="https://cdn.uzum.uz/logo.png"></html>'
    assert parse(page)["images"] == ["https://images.uzum.uz/abc/t_product_540_high.jpg"]
