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
from apps.ai_cards.models import CardBatch, CardDraft
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
    # To'ldiruvchi (ikkinchi) AI so'rovi alohida testlarda yoqiladi.
    # Ko'ruvchi AI (rasm tekshiruvi) ham alohida testlarda yoqiladi.
    settings.AI_CARDS = {**settings.AI_CARDS, "REFINE": False, "VISION": False}


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


def test_duplicate_detected_without_ai_then_forced(staff_client, catalog, fake_gemini, settings, tmp_path):
    """Katalogda shu modelli tovar bor — AI so'rovi sarflanmaydi; «Qayta yaratish» bilan baribir yoziladi."""
    settings.MEDIA_ROOT = str(tmp_path)
    existing = f.product(catalog, model_code="RB38T676FSA")
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    r = c.post(reverse("ai-batch-process", args=[bid])).json()
    assert r["draft"]["status"] == "duplicate" and r["draft"]["product_slug"] == existing.slug
    assert fake_gemini["calls"] == []  # AI chaqirilmadi
    d = CardDraft.objects.get(supplier_sku="A-1")
    assert "Katalogda bor" in d.error
    # xodim ataylab qayta yaratadi — endi AI yozadi, ogohlantirish bilan
    r = c.post(reverse("ai-draft-regenerate", args=[d.id]))
    assert r.json()["status"] == "ready" and "allaqachon bor" in r.json()["warnings"][0]
    assert r.json()["quality"]["score"] < 100
    assert "duplicate" in [i["code"] for i in r.json()["quality"]["issues"]]
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
    p = f.product(catalog, name={"uz": "Samsung RB38 muzlatkichi"}, model_code="RB38T676FSA")
    c = staff_client("content_manager")
    r = c.post(reverse("ai-find-images", args=[p.id]))
    assert r.status_code == 200 and r.json()["images"] == 1
    assert AiCall.objects.count() == 0 and fake_gemini["calls"] == []
    # Boshqa modelli tovarga shu sahifa rasmi olinmaydi (sahifa RB38T676FSA haqida).
    other = f.product(catalog, name={"uz": "Samsung RB34 muzlatkichi"}, model_code="RB34T600FSA")
    r = c.post(reverse("ai-find-images", args=[other.id]))
    assert other.images.count() == 0


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
    assert client.chain("images")[0].name == "groq"  # barcha vazifalar — avval Groq
    # Groq ko'p ishlatilgan bo'lsa ham asosiy bo'lib qoladi (kunlik chegara yo'q)
    AiCall.objects.bulk_create(
        [AiCall(provider="groq", tokens_in=4_000_000, tokens_out=1_000_000) for _ in range(3)]
    )
    assert [p.name for p in client.chain("card")][:2] == ["groq", "cerebras"]
    # xarajat: 12 mln × $0.15 + 3 mln × $0.60 = $3.6; chegara $2 — Groq to'xtaydi, bepullar ishlaydi
    assert client.cost_today() == {"groq": 3.6}
    set_setting("ai_daily_budget_usd", "2")
    assert [p.name for p in client.chain("card")][:2] == ["cerebras", "gemini"]
    set_setting("ai_daily_budget_usd", None)
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


def test_autofix_falls_back_to_ai_image_search(staff_client, catalog, fake_gemini, monkeypatch):
    from apps.ai_cards import page_hints, research

    fake_gemini["card"] = {**CARD, "image_urls": []}
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    assert d.result["images"] == []
    monkeypatch.setattr(page_hints, "fetch", lambda url: {})
    monkeypatch.setattr(research, "read_page_full", lambda url, limit=6000: ("", []))
    fake_gemini["card"] = {"image_urls": ["https://cdn.example.com/rb38.png"]}  # AI internetdan topdi
    c.post(reverse("ai-draft-autofix", args=[d.id]))
    d.refresh_from_db()
    assert d.result["images"] == ["https://cdn.example.com/rb38.png"]
    assert d.warnings[0].startswith("Avto-tuzatish: rasm: 0 → 1 ta")


def test_preview_upload_with_rate_and_markup_then_bulk_publish(
    staff_client, catalog, fake_gemini, settings, tmp_path
):
    """Fayl tanlanganda — valyuta va qatorlar; yuklashda kurs va foyda %; belgilanganlar bir yo'la nashr."""
    settings.MEDIA_ROOT = str(tmp_path)
    c = staff_client("content_manager")
    rows = [["Товар", "Кол", "Цена, $"], ["Холодильник Samsung RB38", 3, 410], ["LG F2V5HS0W", 1, 300]]
    r = c.post(reverse("ai-batch-preview"), {"file": xlsx(rows)}, format="multipart")
    assert r.status_code == 200, r.json()
    p = r.json()
    assert (p["rows_total"], p["currency"], p["with_price"], p["price_max"]) == (2, "USD", 2, "410.00")
    assert p["sample"][0]["name"] == "Холодильник Samsung RB38"
    assert not CardBatch.objects.exists()  # oldindan ko'rish hech narsa saqlamaydi

    r = c.post(
        reverse("ai-batch-list"),
        {"file": xlsx(rows), "currency": "USD", "usd_rate": "12800", "markup_percent": "25"},
        format="multipart",
    )
    b = r.json()
    assert (b["usd_rate"], b["markup_percent"]) == ("12800.00", "25.00")
    c.post(reverse("ai-batch-process", args=[b["id"]]))
    c.post(reverse("ai-batch-process", args=[b["id"]]))
    d1, d2 = CardDraft.objects.order_by("row_number")
    row = next(
        x for x in c.get(reverse("ai-draft-list"), {"batch": b["id"]}).json()["results"] if x["id"] == d1.id
    )
    # 410 × 12 800 = 5 248 000; +25% = 6 560 000
    assert (row["cost_uzs"], row["suggested_price"]) == ("5248000.00", "6560000")
    assert row["image"] and row["category"] == "muzlatkichlar"

    # foiz o'zgarsa — narx qayta hisoblanadi
    c.patch(reverse("ai-batch-settings", args=[b["id"]]), {"markup_percent": "30"}, format="json")
    d2.result = {**d2.result, "category_slug": "", "new_category": None}
    d2.save()
    r = c.post(reverse("ai-batch-publish", args=[b["id"]]), {"ids": [d1.id, d2.id]}, format="json")
    assert r.status_code == 200, r.json()
    out = r.json()
    assert [x["price"] for x in out["published"]] == ["6823000"]  # 5 248 000 × 1.3 = 6 822 400 → 6 823 000
    assert out["failed"][0]["id"] == d2.id and "Kategoriya" in out["failed"][0]["reason"]
    v = Product.objects.get(slug=out["published"][0]["product_slug"]).variants.get()
    assert str(v.price) == "6823000.00" and str(v.cost_price) == "5248000.00"


def test_bulk_publish_without_markup_explains(staff_client, catalog, fake_gemini):
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    out = c.post(reverse("ai-batch-publish", args=[bid]), {"ids": [d.id]}, format="json").json()
    assert not out["published"] and "foyda foizi" in out["failed"][0]["reason"]


def test_bot_protection_images_are_dropped():
    from apps.ai_cards.images import is_junk, urls_in_text
    from apps.ai_cards.services import pick_images

    junk = "https://cdn2.ozone.ru/s3/abt-challenge/incidents/images/warn.png"
    assert is_junk(junk) and not is_junk("https://images.uzum.uz/abc/t_product_540_high.jpg")
    assert urls_in_text(f"![x]({junk})") == []
    assert pick_images([junk]) == ([], [])  # tekshirishga ham yuborilmaydi


def _groq_only(settings, reply, usage=None, seen=None):
    """Faqat Groq ulangan; har so'rovga `reply` matni (va token soni) qaytadi."""
    _free_providers(settings)
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    settings.AI_PROVIDER_CONFIG = {
        **settings.AI_PROVIDER_CONFIG,
        "cerebras": {**settings.AI_PROVIDER_CONFIG["cerebras"], "api_key": ""},
    }

    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        body = {"model": "openai/gpt-oss-120b", "choices": [{"message": {"content": reply}}]}
        if usage:
            body["usage"] = usage
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def test_groq_tokens_and_cost_recorded(staff_client, catalog, settings):
    from apps.ai_cards.models import AiCall

    reply = "```json\n" + json.dumps(CARD, ensure_ascii=False) + "\n```"
    gemini._transport = _groq_only(settings, reply, usage={"prompt_tokens": 6000, "completion_tokens": 1500})
    try:
        c = staff_client("content_manager")
        bid = upload(c).json()["id"]
        c.post(reverse("ai-batch-process", args=[bid]))
        u = c.get(reverse("ai-settings")).json()
    finally:
        gemini._transport = None
    call = AiCall.objects.get()
    assert (call.provider, call.tokens_in, call.tokens_out) == ("groq", 6000, 1500)
    # 6000 × $0.15/1M + 1500 × $0.60/1M = $0.0018
    assert u["cost_today_usd"] == 0.0018 and u["tokens_today"]["groq"] == {"in": 6000, "out": 1500}
    assert next(p for p in u["providers"] if p["name"] == "groq")["tokens_today"] == 7500


def test_image_match_rates_by_evidence():
    """Rasm shu tovarnikimi: model kodi, sahifa sarlavhasi va rasm tavsifi bo'yicha baho."""
    from apps.ai_cards.image_match import Cand, Target, page_level, rank, rate

    t = Target(brand="Samsung", code="QE55Q60DAUXUZ", name="Samsung QE55Q60D televizori Телевизор Samsung")
    page = "https://shop.uz/p/samsung-qe55q60dauxuz"
    title = "Телевизор Samsung QE55Q60DAUXUZ купить"
    # model kodi rasm havolasida yoki tavsifida — kuchli dalil (mintaqaviy varianti ham)
    assert rate(t, Cand("https://cdn.uz/i/qe55q60dauxru-front.jpg", "page", page="https://x.uz/tv")) == 3
    assert rate(t, Cand("https://cdn.uz/i/1.jpg", "page", page, title, alt="Samsung QE55Q60DAU 55")) == 3
    # shu model sahifasining asosiy rasmi — yaxshi; begona sahifaniki — yo'q
    assert rate(t, Cand("https://cdn.uz/i/a.jpg", "main", page, title)) == 2
    assert rate(t, Cand("https://cdn.uz/i/a.jpg", "main", "https://shop.uz/c/tv", "Televizorlar")) == 0
    # qo'shni model (QE55Q70...) sahifasi/rasmi — boshqa tovar
    assert page_level(t, "Samsung QE55Q70DAUXUZ", "https://shop.uz/p/1") == 0
    assert rate(t, Cand("https://cdn.uz/i/qe55q70dau.jpg", "search")) == 0
    # sahifa ichidagi rasm: tavsifi boshqa tovar yoki reklama — yo'q; tavsifsiz — tasdiqlanmagan
    assert rate(t, Cand("https://cdn.uz/i/b.jpg", "page", page, title, alt="LG OLED55C4RLA televizori")) == 0
    assert rate(t, Cand("https://cdn.uz/i/c.jpg", "page", page, title, alt="Muddatli to'lov 12 oy")) == 0
    assert rate(t, Cand("https://cdn.uz/i/d.jpg", "page", page, title)) == 1
    assert (
        rate(t, Cand("https://cdn.uz/i/e.jpg", "page", page, title, alt="Samsung QE55Q60D televizori")) == 2
    )
    # bot himoyasi/logotip — hech qachon; kartochkada bor rasm — tegilmaydi
    assert rate(t, Cand("https://cdn.uz/i/logo-qe55q60dauxuz.png", "main", page, title)) == 0
    assert rate(t, Cand("https://cdn.uz/i/z.jpg", "have")) == 3
    ranked = rank(
        t,
        [
            Cand("https://cdn.uz/i/d.jpg", "page", page, title),
            Cand("https://cdn.uz/i/a.jpg", "main", page, title),
        ],
    )
    assert [r for r, _ in ranked] == [2, 1]
    # kod oxiridagi rang harfisiz yozilgan rasmiy sahifa — shu model; boshqa rang harfi bilan — yo'q
    g = Target(brand="Premier", code="PRM-G60-E31B", name="Premier PRM-G60-E31B gaz plitasi")
    assert page_level(g, "Газовая плита Premier", "https://premier.uz/ru/product/detail/prm-g60-e31") == 1
    assert page_level(g, "Premier PRM-G60-E31W", "https://premier.uz/ru/product/detail/5") == 0
    assert page_level(g, "Premier PRM-G60-E315", "https://premier.uz/ru/product/detail/6") == 0
    # sayt umumiy rasmi (bo'lim rasmi, mavzu fayli) "asosiy rasm" bo'lib kelsa ham — faqat AI tasdiqlasa
    generic = "https://www.lg.com/ae/images/support/select-product-category/washing-machines.jpg"
    assert rate(t, Cand(generic, "main", page, title)) == 1
    assert rate(t, Cand("https://shop.uz/wp-content/themes/x/img/tv.png", "page", page, title)) == 0
    # kirillcha "логотип" (havolada %-kodlangan bo'lsa ham) — hech qachon
    assert (
        rate(
            t,
            Cand(
                "https://sroad.kz/uploads/%D0%9B%D0%BE%D0%B3%D0%BE%D1%82%D0%B8%D0%BF-SRE.png",
                "main",
                page,
                title,
            ),
        )
        == 0
    )
    # model kodi yo'q tovar: nomdagi so'zlar bo'yicha
    n = Target(brand="Artel", code="", name="Artel VCC 0120 changyutgich 2000W")
    assert page_level(n, "Пылесос Artel VCC 0120, 2000W", "https://shop.uz/p/9") == 2
    assert page_level(n, "Artel konditsionerlari", "https://shop.uz/c/ac") == 0


def test_same_picture_in_other_size_is_taken_once():
    """Bir xil surat ikki saytda turli o'lchamda — kartochkaga bittasi (kattasi) tushadi."""
    import io

    from PIL import Image, ImageDraw

    from apps.ai_cards.services import pick_images

    def photo(size, shape, fmt):
        im = Image.new("RGB", (size, size), "white")
        d = ImageDraw.Draw(im)
        box = [size * 0.2, size * 0.3, size * 0.8, size * 0.7]
        (d.rectangle if shape == "tv" else d.ellipse)(box, fill="navy")
        if shape == "tv":
            d.rectangle([size * 0.45, size * 0.7, size * 0.55, size * 0.8], fill="black")
        out = io.BytesIO()
        im.save(out, fmt, quality=80)
        return out.getvalue()

    files = {
        "https://a.com/front-1200.jpg": photo(1200, "tv", "JPEG"),
        "https://b.com/front-600.png": photo(600, "tv", "PNG"),  # o'sha surat, kichik va boshqa turda
        "https://b.com/other.png": photo(800, "round", "PNG"),
    }

    def handler(request):
        body = files.get(str(request.url))
        return httpx.Response(200, content=body) if body else httpx.Response(404)

    gemini._transport = httpx.MockTransport(handler)
    try:
        picked, _ = pick_images(list(files))
    finally:
        gemini._transport = None
    assert picked == ["https://a.com/front-1200.jpg", "https://b.com/other.png"]


def test_short_model_codes_and_guessed_page_images():
    from apps.ai_cards import page_hints, research, smart

    assert smart.model_code_in("Камера Ezviz H1c") == "H1c"
    assert smart.model_code_in("Samsung Galaxy A55 8/256GB") == "A55"
    assert smart.model_code_in("Плеер mp3 Sony") == ""
    assert smart.model_code_in("Телевизор Samsung QE55Q60DAUXUZ S24") == "QE55Q60DAUXUZ"
    # schema.org/og:image yo'q sahifa: HTML'dagi birinchi rasmlar "asosiy rasm" emas — kuchsiz dalil
    hints = page_hints.parse(
        '<html><img src="https://s.uz/u/logo-main.png"><img alt="Artel VCC" src="https://s.uz/u/1.jpg"></html>'
    )
    assert hints["images_guess"] is True and hints["images"] == ["https://s.uz/u/1.jpg"]
    cands = research.page_candidates("https://s.uz/p/1", "Artel VCC 0120", hints, [])
    assert [(c["origin"], c["alt"]) for c in cands] == [("page", "Artel VCC")]
    real = page_hints.parse('<meta property="og:image" content="https://s.uz/u/2.jpg">')
    assert "images_guess" not in real
    assert research.page_candidates("https://s.uz/p/1", "x", real, [])[0]["origin"] == "main"


def test_vision_splits_batch_when_one_image_breaks_the_request(settings):
    """Bitta yaroqsiz rasm tekshiruvni to'xtatmaydi: so'rov bo'linadi, model "yo'q" deb belgilanmaydi."""
    from django.core.cache import cache

    from apps.ai_cards import vision

    cache.clear()
    _free_providers(settings)
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    settings.AI_CARDS = {**settings.AI_CARDS, "VISION": True}
    sizes = []

    def handler(request):
        if str(request.url).endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen/qwen3.8-27b"}]})
        n = len(json.loads(request.content)["messages"][0]["content"]) - 1
        sizes.append(n)
        if n > 1:
            return httpx.Response(400, json={"error": {"message": "failed to process image 2"}})
        text = json.dumps({"images": [{"n": 1, "verdict": "ok", "what": "x"}]})
        return httpx.Response(
            200, json={"model": "qwen/qwen3.8-27b", "choices": [{"message": {"content": text}}]}
        )

    gemini._transport = httpx.MockTransport(handler)
    try:
        shots = [vision.Shot(f"https://x.uz/{i}.png", vision.test_png(64 + i), "png") for i in range(3)]
        res = vision.verify("sinov", "", shots)
    finally:
        gemini._transport = None
    assert res.verdicts == [True, True, True] and sizes == [3, 2, 1, 1, 1]
    assert vision.enabled() and cache.get(vision._MODEL_KEY.format("groq")) == "qwen/qwen3.8-27b"
    assert "failed to process image" in vision.last_error()  # sabab hisobot uchun saqlanadi


def test_image_alt_text_is_read_from_page():
    from apps.ai_cards import images

    text = (
        "![Image 1: Samsung RB38T676FSA oldidan](https://cdn.uz/a/1.jpg) matn "
        '<img alt="Aksiya" src="https://cdn.uz/a/2.png"> https://cdn.uz/a/3.webp'
    )
    urls = images.urls_in_text(text)
    assert urls == ["https://cdn.uz/a/1.jpg", "https://cdn.uz/a/2.png", "https://cdn.uz/a/3.webp"]
    assert [u.alt for u in urls] == ["Samsung RB38T676FSA oldidan", "Aksiya", ""]


def test_images_from_other_product_pages_are_not_taken(
    staff_client, catalog, settings, fake_gemini, no_real_search
):
    """Qidiruvda chiqqan, lekin boshqa model haqidagi sahifaning rasmi kartochkaga tushmaydi."""
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    _free_providers(settings)
    no_real_search["results"] = [
        {
            "title": "Samsung RB34T600FSA",
            "href": "https://shop.example.uz/product/rb34",
            "body": "Muzlatkich",
        },
    ]
    base_handler = gemini._transport.handle_request

    def handler(request):
        url = str(request.url)
        if "groq.test" in url or "cerebras.test" in url:
            text = json.dumps({**CARD, "image_urls": []})
            return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": text}}]})
        if url == "https://shop.example.uz/product/rb34":
            page = (
                '<html><head><script type="application/ld+json">{"@type":"Product",'
                '"name":"Samsung RB34T600FSA","image":["https://cdn.example.com/main-photo.png"]}'
                "</script></head></html>"
            )
            return httpx.Response(200, text=page, headers={"content-type": "text/html"})
        if url == "https://cdn.example.com/main-photo.png":
            fetched.append(url)
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        return base_handler(request)

    fetched = []

    gemini._transport = httpx.MockTransport(handler)
    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    assert d.status == "ready" and d.result["model_code"] == "RB38T676FSA"
    # sahifa RB34 haqida — uning asosiy rasmi olinmadi (hatto yuklab ham ko'rilmadi)
    assert d.result["images"] == [] and fetched == []


def _vision_transport(files, verdicts, seen, status=200):
    """Rasm serveri + Groq: /models va rasmli chat so'roviga `verdicts` bilan javob."""

    def handler(request):
        url = str(request.url)
        if url.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "meta-llama/llama-4-scout-17b-16e-instruct"}]})
        if url.endswith("/chat/completions"):
            body = json.loads(request.content)
            seen.append(body)
            if status != 200:
                return httpx.Response(
                    status, json={"error": {"message": "Rate limit. Please try again in 5m0s"}}
                )
            n = sum(1 for part in body["messages"][0]["content"] if part["type"] == "image_url")
            items = [{"n": i + 1, "verdict": verdicts[i], "what": f"rasm {i + 1}"} for i in range(n)]
            return httpx.Response(
                200,
                json={
                    "model": body["model"],
                    "choices": [{"message": {"content": json.dumps({"images": items})}}],
                    "usage": {"prompt_tokens": 3000, "completion_tokens": 60},
                },
            )
        body = files.get(url)
        return (
            httpx.Response(200, content=body, headers={"content-type": "image/png"})
            if body
            else httpx.Response(404)
        )

    return httpx.MockTransport(handler)


def _vision_case(settings, verdicts, status=200):
    from django.core.cache import cache

    from apps.ai_cards.image_match import Cand, Target
    from apps.ai_cards.services import choose_images

    cache.clear()
    _free_providers(settings)
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    settings.AI_CARDS = {**settings.AI_CARDS, "VISION": True}
    page, title = "https://shop.uz/p/rb38t676fsa", "Samsung RB38T676FSA"
    files = {
        "https://cdn.uz/rb38t676fsa-1.png": _png(1200, 1200, b"1"),  # kuchli dalil (kod havolada)
        "https://cdn.uz/main.png": _png(1000, 1000, b"2"),  # sahifaning asosiy rasmi
        "https://cdn.uz/gallery.png": _png(900, 900, b"3"),  # sahifa ichida, dalilsiz
    }
    cands = [
        Cand("https://cdn.uz/rb38t676fsa-1.png", "page", page, title),
        Cand("https://cdn.uz/main.png", "main", page, title),
        Cand("https://cdn.uz/gallery.png", "page", page, title),
    ]
    seen = []
    gemini._transport = _vision_transport(files, verdicts, seen, status)
    try:
        t = Target(brand="Samsung", code="RB38T676FSA", name="Samsung RB38 muzlatkichi")
        report = {}
        cands.append(
            Cand("https://cdn.uz/other.png", "main", "https://shop.uz/c/all", "Barcha muzlatkichlar")
        )
        picked, warnings = choose_images(
            t, cands, label="Samsung RB38T676FSA", kind="Muzlatkichlar", report=report
        )
    finally:
        gemini._transport = None
    seen.append(report)
    return picked, warnings, seen


def test_vision_removes_wrong_images_and_confirms_unverified(settings):
    """Ko'ruvchi AI: "bad" rasm olinmaydi (dalili bo'lsa ham), dalilsiz rasm "ok" bilan qoladi."""
    from apps.ai_cards.models import AiCall

    picked, warnings, seen = _vision_case(settings, ["ok", "bad", "ok"])
    assert picked == ["https://cdn.uz/rb38t676fsa-1.png", "https://cdn.uz/gallery.png"]
    assert (
        warnings[0].startswith("AI rasmlarni ko'rib tekshirdi: 1 tasi shu tovar emas")
        and "rasm 2" in warnings[0]
    )
    body = seen[0]
    assert body["model"] == "meta-llama/llama-4-scout-17b-16e-instruct"
    parts = body["messages"][0]["content"]
    assert "Muzlatkichlar" in parts[0]["text"] and "Samsung RB38T676FSA" in parts[0]["text"]
    assert [x["type"] for x in parts] == ["text", "image_url", "image_url", "image_url"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    call = AiCall.objects.get()
    assert (call.provider, call.tokens_in) == ("groq", 3000) and "scout" in call.model
    report = seen[-1]
    assert (report["candidates"], report["rejected"], report["ai_removed"]) == (4, 1, 1)
    assert report["seen"] == {
        "https://cdn.uz/rb38t676fsa-1.png": "rasm 3",
        "https://cdn.uz/gallery.png": "rasm 1",
    }
    assert "scout" in report["vision"]


def test_vision_sends_small_jpeg_and_waits_out_short_rate_limit(settings, monkeypatch):
    """Rasm modelga kichraytirilgan JPEG bo'lib ketadi; qisqa (soniyali) limitda kutib, qayta uriniladi."""
    from django.core.cache import cache

    from apps.ai_cards import vision

    cache.clear()
    _free_providers(settings)
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    settings.AI_CARDS = {**settings.AI_CARDS, "VISION": True}
    slept, seen = [], []
    monkeypatch.setattr(vision.time, "sleep", slept.append)

    def handler(request):
        if str(request.url).endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen/qwen3.8-27b"}]})
        seen.append(json.loads(request.content))
        if len(seen) == 1:
            return httpx.Response(
                429, json={"error": {"message": "Rate limit reached. Please try again in 4.2s."}}
            )
        text = json.dumps({"images": [{"n": 1, "verdict": "ok", "what": "violet square"}]})
        return httpx.Response(
            200, json={"model": "qwen/qwen3.8-27b", "choices": [{"message": {"content": text}}]}
        )

    gemini._transport = httpx.MockTransport(handler)
    try:
        res = vision.verify("sinov", "", [vision.Shot("https://x.uz/big.png", vision.test_png(1400), "png")])
    finally:
        gemini._transport = None
    assert res.verdicts == [True] and res.model == "qwen/qwen3.8-27b"
    assert slept == [4.7] and len(seen) == 2 and vision.enabled()
    url = seen[0]["messages"][0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    import base64

    from apps.ai_cards.images import image_size

    assert image_size(base64.b64decode(url.split(",", 1)[1])) == (512, 512)


def test_autofix_rechecks_images_ai_could_not_see(staff_client, catalog, fake_gemini, settings):
    """AI ko'ra olmagan (limit) kartochka: avto-tuzatish rasmlarni ko'rib, noto'g'risini olib tashlaydi."""
    from django.core.cache import cache

    from apps.ai_cards.services import needs_autofix

    c = staff_client("content_manager")
    bid = upload(c).json()["id"]
    c.post(reverse("ai-batch-process", args=[bid]))
    d = CardDraft.objects.get(supplier_sku="A-1")
    wrong = "https://cdn.example.com/x/thumb-rb38.png"
    d.result = {
        **d.result,
        "images": [*d.result["images"], wrong],
        "image_report": {"candidates": 5, "rejected": 1, "vision": "", "vision_error": "Groq limiti tugagan"},
    }
    d.save()
    assert needs_autofix(d)

    cache.clear()
    _free_providers(settings)
    settings.AI_CARDS = {**settings.AI_CARDS, "VISION": True}
    base_handler = gemini._transport.handle_request

    def handler(request):
        url = str(request.url)
        if url.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen/qwen3.8-27b"}]})
        if url.endswith("/chat/completions"):
            body = json.loads(request.content)
            if isinstance(body["messages"][0]["content"], list):  # rasmli so'rov — ko'ruvchi AI
                items = [
                    {"n": 1, "verdict": "ok", "what": "fridge"},
                    {"n": 2, "verdict": "bad", "what": "banner"},
                ]
                text = json.dumps({"images": items})
            else:
                text = "{}"
            return httpx.Response(
                200, json={"model": body["model"], "choices": [{"message": {"content": text}}]}
            )
        return base_handler(request)

    gemini._transport = httpx.MockTransport(handler)
    r = c.post(reverse("ai-draft-autofix", args=[d.id]))
    assert r.status_code == 200, r.json()
    d.refresh_from_db()
    assert wrong not in d.result["images"] and "https://cdn.example.com/rb38.png" in d.result["images"]
    report = d.result["image_report"]
    assert (
        report["vision"] == "qwen/qwen3.8-27b" and "vision_error" not in report and report["ai_removed"] == 1
    )
    assert report["seen"] == {"https://cdn.example.com/rb38.png": "fridge"}
    assert "AI rasmlarni ko'rdi: 1 tasi shu tovar emas" in d.warnings[0]


def test_unverified_image_dropped_when_vision_says_no_or_is_down(settings):
    # Eng kuchsiz dalilli rasm birinchi ko'rsatiladi: dalilsiz (galereya), asosiy rasm, kodi yozilgani.
    picked, _, _ = _vision_case(settings, ["bad", "ok", "ok"])
    assert picked == ["https://cdn.uz/rb38t676fsa-1.png", "https://cdn.uz/main.png"]
    # Ko'ruvchi AI limiti tugagan: dalilli rasmlar qoladi, dalilsizi olinmaydi; keyingi safar urinilmaydi.
    from apps.ai_cards import vision

    picked, warnings, seen = _vision_case(settings, [], status=429)
    assert picked == ["https://cdn.uz/rb38t676fsa-1.png", "https://cdn.uz/main.png"]
    assert len(seen) == 2 and not vision.enabled()  # 1 ta so'rov + hisobot
    assert not any(w.startswith("AI rasmlarni") for w in warnings)
    assert seen[-1]["vision"] == "" and seen[-1]["unconfirmed"] == 1
    assert "Groq limiti tugagan" in seen[-1]["vision_error"]


def test_web_image_search_not_sent_to_non_search_ai(settings):
    """Groq/Cerebras qidira olmaydi — ularga "rasm qidir" so'rovi yuborilmaydi (havola o'ylab topmasin)."""
    from apps.ai_cards import client

    seen = []
    gemini._transport = _groq_only(settings, "{}", seen=seen)
    try:
        with pytest.raises(client.AiError):
            client.generate(lambda search: "qidir" if search else None, task="images")
    finally:
        gemini._transport = None
    assert seen == []


def test_internal_addresses_are_never_fetched(staff_client, catalog):
    """SSRF himoyasi: ichki tarmoq manzillari (localhost, 10.x, bulut metadata) yuklanmaydi."""
    from apps.ai_cards import images, page_hints
    from apps.core.net import is_public_url

    for url in (
        "http://127.0.0.1:8000/admin/",
        "http://localhost/x.png",
        "http://10.0.0.5/a.jpg",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/a.png",
        "ftp://example.com/a.png",
        "http://db.internal/x",
    ):
        assert not is_public_url(url), url
    assert is_public_url("https://8.8.8.8/a.png")
    hits = []

    def handler(request):
        hits.append(str(request.url))
        if "redirect.example.com" in str(request.url):  # ochiq sayt ichki manzilga yo'naltiradi
            return httpx.Response(302, headers={"location": "http://169.254.169.254/secret.png"})
        return httpx.Response(200, content=_png(600, 600), headers={"content-type": "image/png"})

    gemini._transport = httpx.MockTransport(handler)
    try:
        f = images.fetch("http://169.254.169.254/latest/meta-data/x.png")
        assert not f.ok and "ichki tarmoq" in f.reason
        assert page_hints.fetch("http://127.0.0.1:8000/admin/") == {}
        r = staff_client("content_manager").post(
            reverse("ai-draft-from-url"), {"url": "http://10.0.0.5/product/1"}, format="json"
        )
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad_url"
        assert not images.fetch("https://redirect.example.com/a.png").ok
        assert images.fetch("https://cdn.example.com/ok.png").ok  # oddiy ochiq manzil ishlaydi
    finally:
        gemini._transport = None
    assert not any("169.254" in h or "127.0.0.1" in h or "10.0.0.5" in h for h in hits)


def test_understand_supplier_rows():
    """Qatordan brend/model kodi; ortiqcha so'zlar qidiruvga tushmaydi; mintaqaviy variantlar."""
    from apps.ai_cards import smart

    brands = ["Samsung", "Premier", "Artel"]
    u = smart.understand(
        "Телевизор Samsung QE75Q7FAAUXUZ QLED 4K SMART 2025 MODEL  VIETNAM", known_brands=brands
    )
    assert (u.brand, u.model_code) == ("Samsung", "QE75Q7FAAUXUZ")
    assert u.queries == ["Samsung QE75Q7FAAUXUZ", "Samsung QE75Q7FAAUXUZ характеристики"]
    assert u.fallback_queries[0] == "Samsung QE75Q7FAAU" and "Samsung QE75Q7FAAUXRU" in u.fallback_queries
    u = smart.understand("Телевизор TCL TV TCL 65P635 Чёрный 4K SMART UHD", known_brands=brands)
    assert (u.brand, u.model_code) == ("TCL", "65P635")
    u = smart.understand("Газ Плита PREMIER  PRM-G60-E31B 60x60", known_brands=brands)
    assert (u.brand, u.model_code) == ("Premier", "PRM-G60-E31B")
    u = smart.understand(
        "Интерактивная панель PREMIER 65PRM5500IFP ddr 8gb ssd 128gb 4k uhd", known_brands=brands
    )
    assert u.model_code == "65PRM5500IFP"  # 128gb, 4k — model kodi emas
    u = smart.understand("Холодильник Artel HD 455 RWENF NEW MODEL 2026", known_brands=brands)
    assert u.model_code == "" and u.queries[0] == "Холодильник Artel HD 455 RWENF"
    assert smart.code_variants("HW-Q600C/RU") == ["HW-Q600C"]


def test_enrich_and_quality():
    from apps.ai_cards import smart

    def spec(name, value):
        return {
            "group": {"uz": "Asosiy", "ru": ""},
            "name": {"uz": name, "ru": ""},
            "value": {"uz": value, "ru": ""},
        }

    r = {
        "name": {"uz": "Samsung UE55 televizori", "ru": "Телевизор Samsung UE55"},
        "description": {"uz": "x" * 500, "ru": "y" * 500},
        "category_slug": "televizorlar",
        "model_code": "UE55",
        "images": ["a", "b", "c"],
        "specs": [
            spec("Og'irligi (qadoq bilan)", "21 kg"),
            spec("Og'irligi", "15,4 kg"),
            spec("O'lchamlari", "1232 × 711 × 60 mm"),
            *[spec(f"X{i}", "1") for i in range(8)],
        ],
    }
    q = smart.quality(r)
    assert {i["code"] for i in q["issues"]} == {"no_weight", "no_dimensions"} and q["score"] == 85
    assert smart.enrich(r) == ["og'irlik", "o'lcham", "yirik texnika"]
    assert r["weight_kg"] == 15.4 and r["dimensions_cm"] == {"length": 71, "width": 6, "height": 123}
    assert smart.quality(r) == {"score": 100, "issues": []}
    r["specs"][0]["name"]["uz"] = "Вес"
    assert [i["code"] for i in smart.quality(r)["issues"]] == ["cyrillic_in_uz"]


def _two_step_ai(settings, first, second, seen):
    """Faqat Groq: birinchi so'rovga `first`, keyingisiga `second` (JSON) qaytadi."""
    _free_providers(settings)
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    settings.AI_PROVIDER_CONFIG = {
        **settings.AI_PROVIDER_CONFIG,
        "cerebras": {**settings.AI_PROVIDER_CONFIG["cerebras"], "api_key": ""},
    }

    def handler(request):
        if "groq.test" not in str(request.url):
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        seen.append(json.loads(request.content)["messages"][-1]["content"])
        reply = first if len(seen) == 1 else second
        text = "```json\n" + json.dumps(reply, ensure_ascii=False) + "\n```"
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": text}}]})

    return httpx.MockTransport(handler)


def test_refine_fills_missing_fields(staff_client, catalog, settings, no_real_search):
    """Kartochkada og'irlik/o'lcham/xususiyat yetishmasa — ikkinchi so'rov faqat shularni to'ldiradi."""
    settings.AI_CARDS = {**settings.AI_CARDS, "REFINE": True}
    no_real_search["results"] = [
        {"href": "https://shop.uz/rb38", "title": "RB38", "body": "Samsung RB38T676FSA"}
    ]
    first = {
        **CARD,
        "weight_kg": None,
        "dimensions_cm": None,
        "name_uz": "Samsung RB38 холодильник",
        "specs": [{"name_uz": "Тип", "value_uz": "Ikki kamerali"}],
    }
    second = {
        "weight_kg": 70.5,
        "dimensions_cm": {"length": 60, "width": 66, "height": 203},
        "specs": [{"group_uz": "Asosiy", "name_uz": f"Xususiyat {i}", "value_uz": str(i)} for i in range(12)],
        "uz_fixes": {"Samsung RB38 холодильник": "Samsung RB38 muzlatkichi", "Тип": "Turi"},
        "description_uz": "Batafsil tavsif. " * 40,
    }
    seen = []
    gemini._transport = _two_step_ai(settings, first, second, seen)
    try:
        c = staff_client("content_manager")
        bid = upload(c).json()["id"]
        c.post(reverse("ai-batch-process", args=[bid]))
    finally:
        gemini._transport = None
    d = CardDraft.objects.get(supplier_sku="A-1")
    r = d.result
    assert len(seen) == 2 and "FAQAT shularni" in seen[1] and "weight_kg" in seen[1] and "uz_fixes" in seen[1]
    assert r["weight_kg"] == 70.5 and r["dimensions_cm"]["height"] == 203 and r["is_bulky"]
    assert r["name"]["uz"] == "Samsung RB38 muzlatkichi" and r["specs"][0]["name"]["uz"] == "Turi"
    assert len(r["specs"]) == 13 and len(r["description"]["uz"]) > 400
    assert any("qo'shimcha so'rov bilan to'ldirdi" in w for w in d.warnings)
    from apps.ai_cards.models import AiCall

    assert AiCall.objects.count() == 2


def test_not_found_retries_with_regional_variant(staff_client, catalog, settings, monkeypatch):
    """Topilmadi → model kodining boshqa bozor varianti (UXUZ → ...U / UXRU) bilan yana bir urinish."""
    from apps.ai_cards import research

    queries = []

    def search(q, max_results=8):
        queries.append(q)
        return [{"href": "https://shop.ru/q7f", "title": q, "body": "Samsung QE75Q7FAAUXRU 75"}]

    monkeypatch.setattr(research, "web_search", search)
    monkeypatch.setattr(research, "read_page_full", lambda url, limit=6000: ("QLED 75", []))
    seen = []
    card = {**CARD, "model_code": "", "name_uz": "Samsung QE75Q7FAAUXUZ televizori"}
    gemini._transport = _two_step_ai(settings, {"found": False}, card, seen)
    try:
        c = staff_client("content_manager")
        rows = [
            ["Товар", "Кол", "Цена, $"],
            ["Телевизор Samsung QE75Q7FAAUXUZ QLED 4K SMART 2025 MODEL VIETNAM", 1, 900],
        ]
        bid = upload(c, rows).json()["id"]
        r = c.post(reverse("ai-batch-process", args=[bid])).json()
    finally:
        gemini._transport = None
    assert queries[0] == "Samsung QE75Q7FAAUXUZ"  # ortiqcha so'zlarsiz
    assert "Samsung QE75Q7FAAU" in queries and len(seen) == 2
    d = CardDraft.objects.get(pk=r["draft"]["id"])
    assert d.status == "ready" and d.result["model_code"] == "QE75Q7FAAUXUZ"  # fayldagi kod saqlanadi
    assert "boshqa bozor varianti" in d.warnings[0]


def test_autofix_enriches_and_refines_existing_card(staff_client, catalog, settings, no_real_search):
    """Avval yaratilgan kartochka: avto-tuzatish og'irlikni xususiyatdan oladi, qolganini AI'dan so'raydi."""
    no_real_search["results"] = [
        {"href": "https://shop.uz/rb38", "title": "RB38", "body": "Samsung RB38T676FSA"}
    ]
    first = {
        **CARD,
        "weight_kg": None,
        "dimensions_cm": None,
        "description_uz": "Tavsif. " * 80,
        "specs": [{"name_uz": "Og'irligi", "value_uz": "70,5 kg"}],
    }
    second = {
        "dimensions_cm": {"length": 60, "width": 66, "height": 203},
        "specs": [{"name_uz": f"Xususiyat {i}", "value_uz": str(i)} for i in range(10)],
    }
    seen = []
    gemini._transport = _two_step_ai(settings, first, second, seen)
    try:
        c = staff_client("content_manager")
        bid = upload(c).json()["id"]
        c.post(reverse("ai-batch-process", args=[bid]))  # REFINE o'chiq: bitta so'rov
        d = CardDraft.objects.get(supplier_sku="A-1")
        assert d.result["weight_kg"] == 70.5 and not any(d.result["dimensions_cm"].values())  # enrich ishladi
        settings.AI_CARDS = {**settings.AI_CARDS, "REFINE": True}
        r = c.post(reverse("ai-draft-autofix", args=[d.id])).json()
    finally:
        gemini._transport = None
    assert len(seen) == 2 and "weight_kg" not in seen[1].split("FAQAT shularni")[1].split("---")[0]
    assert r["result"]["dimensions_cm"]["height"] == 203 and len(r["result"]["specs"]) == 11
    assert "to'ldirildi" in r["warnings"][0]


def test_partial_dimensions_count_as_missing():
    from apps.ai_cards import smart

    r = {"dimensions_cm": {"length": 122, "width": 71, "height": 0}}
    assert "no_dimensions" in [i["code"] for i in smart.quality(r)["issues"]]
    r["specs"] = [
        {
            "group": {"uz": "A"},
            "name": {"uz": "O'lchamlari", "ru": ""},
            "value": {"uz": "122 x 71 x 8 sm", "ru": ""},
        }
    ]
    assert "o'lcham" in smart.enrich(r) and all(r["dimensions_cm"].values())
