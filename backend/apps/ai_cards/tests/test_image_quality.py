"""Rasm sifati (AI'siz): baho, yaroqsiz rasmlar, do'kon uchun tekislash, rang mosligi."""

import io

import pytest
from PIL import Image, ImageDraw

from apps.ai_cards import image_match, image_quality


def _bytes(im, fmt="PNG") -> bytes:
    out = io.BytesIO()
    im.convert("RGB").save(out, fmt, quality=90)
    return out.getvalue()


def product(size=(1000, 1000), box=(300, 200, 700, 800), bg="white", body=(40, 60, 90)):
    """Sun'iy "katalog surati": fonda to'rtburchak tovar, ichida mayda chiziqlar (tafsilot)."""
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    d.rectangle(box, fill=body, outline=(190, 190, 190))
    for y in range(box[1] + 20, box[3] - 10, 14):
        d.line((box[0] + 20, y, box[2] - 20, y), fill=(150, 160, 180), width=2)
    return im


def test_clean_catalogue_shot_scores_higher_than_small_or_blurry_copies():
    clean = image_quality.analyse(_bytes(product()))
    small = image_quality.analyse(_bytes(product().resize((400, 400))))
    blurry = image_quality.analyse(_bytes(product().resize((160, 160)).resize((1000, 1000), Image.BICUBIC)))
    assert clean.clean and clean.white_bg == 1.0 and not clean.problem
    assert clean.score > small.score and clean.score > blurry.score
    assert clean.sharp > blurry.sharp


@pytest.mark.parametrize(
    ("image", "reason"),
    [
        (product((1600, 400), (100, 100, 400, 300)), "banner"),
        (Image.new("RGB", (800, 800), "white"), "bo'sh rasm"),
        (product(box=(480, 480, 540, 560)), "deyarli bo'sh"),
    ],
)
def test_banners_and_empty_pictures_are_flagged(image, reason):
    assert reason in image_quality.analyse(_bytes(image)).problem


def test_unreadable_file_is_not_analysed():
    assert image_quality.analyse(b"<html>not an image</html>") is None
    assert image_quality.normalize(b"<html>not an image</html>") is None


def test_normalize_trims_white_border_and_makes_the_picture_square():
    # Tovar keng kadrning chap tomonida: natija — kvadrat, tovar markazda, atrofida bir xil hoshiya.
    data, ext = image_quality.normalize(_bytes(product((1200, 700), (150, 100, 500, 600)), "JPEG"))
    out = Image.open(io.BytesIO(data))
    assert ext == "jpg" and out.size[0] == out.size[1]
    q = image_quality.analyse(data)
    assert q.fill > 0.45 and q.white_bg == 1.0
    assert out.getpixel((2, 2)) == (255, 255, 255)


def test_normalize_keeps_light_grey_background_colour_and_limits_size():
    data, _ = image_quality.normalize(
        _bytes(product((3000, 2000), (400, 300, 1600, 1700), bg=(245, 245, 245)))
    )
    out = Image.open(io.BytesIO(data))
    assert max(out.size) <= image_quality.MAX_SIDE and out.size[0] == out.size[1]
    assert all(abs(c - 245) <= 3 for c in out.getpixel((3, 3)))


def test_normalize_leaves_good_and_non_catalogue_pictures_alone():
    assert image_quality.normalize(_bytes(product(box=(60, 60, 940, 940)))) is None  # allaqachon tekis
    scene = Image.effect_noise((900, 600), 50).convert("RGB")  # xonadagi surat: fon oq emas
    assert image_quality.normalize(_bytes(scene)) is None
    # Oq tovar oq fonda: faqat kichik qora dastasi ko'rinadi — kesilmaydi (tovarni kesib yubormaslik uchun).
    white = Image.new("RGB", (1000, 1400), "white")
    ImageDraw.Draw(white).rectangle((480, 600, 520, 700), fill=(30, 30, 30))
    assert image_quality.normalize(_bytes(white)) is None


def test_colour_is_read_from_the_listing_and_compared_with_the_photo():
    assert image_match.colour_of("Samsung RB38 muzlatkichi, qora") == "black"
    assert image_match.colour_of("Холодильник LG белый") == "white"
    assert image_match.colour_of("Artel konditsioner inox") == "grey"
    assert image_match.colour_of("iPhone 15 black / white") == ""  # ikki rang — noaniq
    assert image_match.colour_of("Black+Decker dazmol", skip="Black+Decker") == ""  # brend nomi rang emas
    target = image_match.Target(brand="Samsung", code="RB38T676FSA", name="Samsung RB38 qora muzlatkich")
    assert target.colour == "black"
    assert image_match.colours_clash("black", "white") and image_match.colours_clash("white", "Blue")
    # Kumush/kulrang hech narsaga zid emas; yaqin ranglar ham (oltin ↔ jigarrang); noma'lum rang ham.
    assert not image_match.colours_clash("black", "silver")
    assert not image_match.colours_clash("gold", "brown")
    assert not image_match.colours_clash("black", "") and not image_match.colours_clash("", "white")


def _vision_setup(settings):
    from django.core.cache import cache

    cache.clear()
    settings.AI_PROVIDER_CONFIG = {
        **settings.AI_PROVIDER_CONFIG,
        "groq": {
            **settings.AI_PROVIDER_CONFIG.get("groq", {}),
            "api_key": "k",
            "base_url": "https://groq.test/v1",
        },
    }
    settings.GEMINI = {**settings.GEMINI, "API_KEY": ""}
    settings.AI_CARDS = {**settings.AI_CARDS, "VISION": True}


@pytest.mark.django_db
def test_other_colour_variant_is_dropped_and_sharpest_clean_shot_goes_first(settings):
    """Ro'yxatda "qora" — AI suratda oq tovarni ko'rsa, u boshqa rangdagi variant: olinmaydi. Qolganlardan
    eng sifatli toza surat (kattasi) asosiy rasm bo'ladi."""
    import json

    import httpx

    from apps.ai_cards import gemini
    from apps.ai_cards.image_match import Cand, Target
    from apps.ai_cards.services import choose_images

    _vision_setup(settings)
    page, title = "https://shop.uz/p/rb38t676fsa", "Samsung RB38T676FSA"
    files = {
        "https://cdn.uz/white.png": _bytes(product(body=(235, 235, 235), box=(250, 150, 750, 850))),
        # boshqa rakurs (yotiq) — "bir xil surat" deb tashlanmasligi uchun
        "https://cdn.uz/small.png": _bytes(product(box=(150, 300, 850, 700)).resize((500, 500))),
        "https://cdn.uz/big.png": _bytes(product(box=(280, 180, 720, 820))),
    }

    def seen_colour(part: dict) -> str:
        """Soxta "ko'ruvchi AI": yuborilgan rasm markazidagi rangga qarab javob beradi."""
        import base64

        data = base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
        im = Image.open(io.BytesIO(data)).convert("L")
        cx, cy = im.width // 2, im.height // 2
        centre = list(im.crop((cx - 20, cy - 20, cx + 20, cy + 20)).tobytes())
        return "white" if sum(centre) / len(centre) > 150 else "black"

    def handler(request):
        url = str(request.url)
        if url.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen/qwen3.8-27b"}]})
        if url.endswith("/chat/completions"):
            body = json.loads(request.content)
            assert "Listed colour: black" in body["messages"][0]["content"][0]["text"]
            parts = body["messages"][0]["content"][1:]
            items = [
                {"n": i + 1, "verdict": "ok", "type": "main", "color": seen_colour(part), "what": "fridge"}
                for i, part in enumerate(parts)
            ]
            text = json.dumps({"images": items})
            return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": text}}]})
        body = files.get(url)
        return httpx.Response(200, content=body) if body else httpx.Response(404)

    gemini._transport = httpx.MockTransport(handler)
    try:
        report = {}
        picked, _ = choose_images(
            Target(brand="Samsung", code="RB38T676FSA", name="Samsung RB38 muzlatkich qora"),
            [Cand(u, "main", page, title) for u in files],
            label="Samsung RB38T676FSA",
            report=report,
        )
    finally:
        gemini._transport = None
    assert picked == ["https://cdn.uz/big.png", "https://cdn.uz/small.png"]
    assert report["colour_dropped"] == 1


def test_downloaded_picture_is_squared_for_the_shop(settings):
    import httpx

    from apps.ai_cards import gemini
    from apps.ai_cards.services import _download

    wide = _bytes(product((1200, 700), (150, 100, 500, 600)), "JPEG")
    gemini._transport = httpx.MockTransport(lambda request: httpx.Response(200, content=wide))
    try:
        saved = _download("https://cdn.uz/wide.jpg")
    finally:
        gemini._transport = None
    out = Image.open(io.BytesIO(saved.read()))
    assert saved.name.endswith(".jpg") and out.size[0] == out.size[1]


def test_vision_sends_at_most_three_pictures_per_request(settings):
    """Ko'ruvchi model bitta so'rovda 3 tadan ortiq rasm olmaydi — 5 ta rasm ikki so'rovga bo'linadi."""
    import json

    import httpx

    from apps.ai_cards import gemini, vision

    _vision_setup(settings)
    sizes = []

    def handler(request):
        if str(request.url).endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen/qwen3.8-27b"}]})
        n = len(json.loads(request.content)["messages"][0]["content"]) - 1
        sizes.append(n)
        if n > vision.PER_REQUEST:
            return httpx.Response(400, json={"error": {"message": "Too many images provided."}})
        items = [{"n": i + 1, "verdict": "ok", "type": "main", "color": "", "what": "x"} for i in range(n)]
        text = json.dumps({"images": items})
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": text}}]})

    shots = [
        vision.Shot(f"https://x.uz/{i}.png", _bytes(product(box=(100 + i * 40, 100, 600, 800))), "png")
        for i in range(5)
    ]
    gemini._transport = httpx.MockTransport(handler)
    try:
        res = vision.verify("sinov", "", shots)
    finally:
        gemini._transport = None
    assert sizes == [3, 2] and res.verdicts == [True] * 5
