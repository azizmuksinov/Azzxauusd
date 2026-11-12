"""Ko'ruvchi AI: tanlangan rasmlarda haqiqatan shu tovar tasvirlanganini tekshirish.

Matn bo'yicha dalillar (image_match) "bu rasm shu model sahifasidan" deydi, lekin rasmda nima borligini
ko'rmaydi: banner, o'lcham jadvali, aksessuar yoki umuman boshqa tovar bo'lishi mumkin. Shu modul rasmlarni
ko'ra oladigan modelga (Groq'dagi vision modeli, zaxirada Gemini) yuboradi va har biriga "ha/yo'q" oladi.

Hammasi eng yaxshi urinish: xizmat ishlamasa yoki limiti tugasa — None qaytadi va chaqiruvchi faqat
ishonchli (dalilli) rasmlarni qoldiradi.
"""

import base64
import io
import logging
import re
import struct
import time
import zlib
from dataclasses import dataclass, field

import httpx
from django.conf import settings
from django.core.cache import cache

from . import gemini

logger = logging.getLogger(__name__)

MAX_IMAGES = 3  # bitta so'rovda (bepul tarifning daqiqalik token chegarasiga sig'ishi uchun)
BUDGET = 25  # soniya: bitta tekshiruvga (barcha urinishlar bilan) ajratilgan vaqt
INLINE_MAX = 1_200_000  # bayt: bundan katta rasm havola bilan yuboriladi
SIDE = 512  # px: modelga shu o'lchamgacha kichraytirib yuboriladi (token va limit tejaladi)
SHORT_WAIT = 6  # soniya: daqiqalik limit shu vaqt ichida tiklansa — kutib, bir marta qayta uriniladi
_ERROR_KEY = "ai_vision_error"
MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}
_MODEL_KEY = "ai_vision_model:{}"
_COOLDOWN = "ai_cooldown:vision:{}"
_VISION_HINT = re.compile(r"scout|maverick|vision|llava|pixtral|qwen-?3|qwen-?vl|gemma-?3", re.I)

PROMPT = """You check product photos for an online home-appliance and electronics store.
Product: "{label}".{kind}
There are {n} images, in order (1..{n}). For each image decide:
- "ok": a photo or render of this product: the same kind of product, and the same brand and model as far as
  can be seen. Any angle, an open/inside view, the product in a room, or the product with its box are fine.
- "bad": a different kind of product; only an accessory, remote or spare part; a banner, advert or collage
  with promo text; a logo or icon; a size chart, table, diagram or screenshot; a person without the product;
  or a clearly different brand or model (another brand's logo or another model name is visible).
If you are not sure, answer "ok" only when the product kind clearly matches.
Also give the image "type":
- "main": the product alone on a plain (usually white) background — a clean catalogue shot;
- "scene": the product in a room, in use, or with people;
- "info": an image dominated by text, feature callouts, specs or several pictures combined;
- "box": mostly the packaging.
Reply with JSON only:
{{"images":[{{"n":1,"verdict":"ok","type":"main","what":"short description, 3-6 words"}}]}}"""


@dataclass
class Result:
    verdicts: list[bool | None]
    notes: list[str] = field(default_factory=list)  # har rasmda nima ko'rindi (qisqa)
    provider: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    kinds: list[str] = field(default_factory=list)  # har rasm turi: main | scene | info | box | ""


KINDS = ("main", "scene", "info", "box")


@dataclass
class Shot:
    url: str
    content: bytes = b""
    ext: str = ""


def enabled() -> bool:
    return bool(settings.AI_CARDS.get("VISION", True)) and bool(_providers())


def last_error() -> str:
    """Oxirgi muvaffaqiyatsiz urinish sababi (xodimga ko'rsatish uchun); muvaffaqiyatda tozalanadi."""
    return cache.get(_ERROR_KEY) or ""


def _fail(reason: str) -> None:
    cache.set(_ERROR_KEY, reason[:200], 600)


def clear_error() -> None:
    cache.delete(_ERROR_KEY)


def _wait_seconds(message: str) -> float:
    """429 xabaridagi kutish vaqti ("try again in 7.5s", "in 2m10s"); topilmasa — 60."""
    m = re.search(
        r"(?:try again in|retry after)\s*(?:(\d+)h)?\s*(?:(\d+)m(?!s))?\s*(?:([\d.]+)s)?", message, re.I
    )
    if not m or not any(m.groups()):
        return 60.0
    h, mi, s = (float(x) if x else 0.0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def _shrink(s: "Shot") -> tuple[bytes, str] | None:
    """Rasmni kichraytirilgan JPEG'ga o'tkazish (AVIF/WebP ham). Bo'lmasa — asl fayl (mos turda bo'lsa)."""
    if not s.content:
        return None
    try:
        from PIL import Image

        with Image.open(io.BytesIO(s.content)) as im:
            im.load()
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                flat = Image.new("RGB", im.size, "white")
                flat.paste(im, mask=im.split()[-1])
                im = flat
            else:
                im = im.convert("RGB")
            im.thumbnail((SIDE, SIDE))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=82)
            return out.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 — fayl buzuq yoki o'qilmaydigan turda: asl fayl (kichik bo'lsa)
        if s.ext in MIME and len(s.content) <= INLINE_MAX:
            return s.content, MIME[s.ext]
    return None


def _providers() -> list[str]:
    out = []
    if (settings.AI_PROVIDER_CONFIG.get("groq") or {}).get("api_key"):
        out.append("groq")
    if settings.GEMINI.get("API_KEY"):
        out.append("gemini")
    return [p for p in out if not cache.get(_COOLDOWN.format(p))]


def _parse(text: str, n: int) -> tuple[list[bool | None], list[str], list[str]]:
    data = gemini.extract_json(text)
    verdicts: list[bool | None] = [None] * n
    notes = [""] * n
    kinds = [""] * n
    for item in data.get("images") or []:
        if not isinstance(item, dict):
            continue
        try:
            i = int(item.get("n")) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= i < n:
            v = str(item.get("verdict", "")).strip().lower()
            verdicts[i] = True if v == "ok" else False if v == "bad" else None
            notes[i] = str(item.get("what") or "")[:80]
            kind = str(item.get("type") or "").strip().lower()
            kinds[i] = kind if kind in KINDS else ""
    return verdicts, notes, kinds


# --- Groq (OpenAI-mos) ---
def _groq_models(cfg: dict) -> list[str]:
    """Sinab ko'riladigan modellar: sozlamadagi ro'yxat (xizmatda borlari oldin), keyin nomiga ko'ra
    "ko'ruvchi" bo'lishi mumkin bo'lganlar. Ishlagani 6 soat eslab qolinadi."""
    if hit := cache.get(_MODEL_KEY.format("groq")):
        return [] if hit == "-" else [hit]
    wanted = list(settings.AI_CARDS.get("VISION_MODELS") or [])
    try:
        with gemini.client(timeout=15) as c:
            r = c.get(
                f"{cfg['base_url'].rstrip('/')}/models", headers={"Authorization": f"Bearer {cfg['api_key']}"}
            )
        ids = [m.get("id", "") for m in r.json().get("data", [])] if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        ids = []
    if not ids:
        return wanted
    known = [m for m in wanted if m in ids]
    guessed = [m for m in ids if m not in wanted and _VISION_HINT.search(m)]
    return [*known, *guessed][:4]


# Xato modelning o'ziga tegishli (yo'q, o'chirilgan, rasm qabul qilmaydi) — boshqa modelni sinash kerak.
_MODEL_PROBLEM = re.compile(
    r"model.{0,80}(not found|does not exist|decommission|not supported|no longer|not have access)"
    r"|does not support|must be a string|not a vision|multimodal|image input",
    re.I,
)
SPLIT = "split"  # so'rov sig'madi yoki rasmlardan biri yaroqsiz — kichikroq bo'laklarga bo'lib ko'rish kerak


def _groq(prompt: str, images: list[tuple[bytes, str]], *, retried: bool = False, fresh: bool = False):
    """Result | None (xizmat ishlamadi) | SPLIT. `images` — kichraytirilgan (bayt, MIME) juftlari."""
    cfg = settings.AI_PROVIDER_CONFIG["groq"]
    content: list[dict] = [{"type": "text", "text": prompt}]
    for data, mime in images:
        url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        content.append({"type": "image_url", "image_url": {"url": url}})
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    remembered = bool(cache.get(_MODEL_KEY.format("groq")))
    models = _groq_models(cfg)
    unfit = 0
    for model in models:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": 500,
        }
        try:
            with gemini.client(timeout=20) as c:
                r = c.post(f"{cfg['base_url'].rstrip('/')}/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("Rasm ko'rigi (Groq %s): aloqa yo'q — %s", model, exc)
            _fail("Groq bilan aloqa yo'q")
            return None
        if r.status_code == 200:
            data = r.json()
            text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            u = data.get("usage") or {}
            try:
                verdicts, notes, kinds = _parse(text, len(images))
            except gemini.GeminiError:
                logger.warning("Rasm ko'rigi (Groq %s): javob JSON emas: %r", model, text[:200])
                _fail("model javobi tushunarsiz")
                return None
            cache.set(_MODEL_KEY.format("groq"), model, 6 * 3600)
            return Result(
                verdicts,
                notes,
                "groq",
                data.get("model") or model,
                int(u.get("prompt_tokens") or 0),
                int(u.get("completion_tokens") or 0),
                kinds,
            )
        try:
            err = r.json().get("error") or {}
            msg = str(err.get("message") if isinstance(err, dict) else err)[:300]
        except ValueError:
            msg = r.text[:300]
        if r.status_code == 429:
            wait = _wait_seconds(msg)
            if wait <= SHORT_WAIT and not retried:
                time.sleep(wait + 0.5)  # daqiqalik limit: biroz kutib, bir marta qayta urinamiz
                return _groq(prompt, images, retried=True, fresh=fresh)
            cache.set(_COOLDOWN.format("groq"), True, int(min(max(wait, 30), 6 * 3600)))
            _fail(f"Groq limiti tugagan (taxminan {int(wait)} soniyadan keyin tiklanadi)")
            return None
        if r.status_code in (400, 404) and _MODEL_PROBLEM.search(msg):
            logger.info("Rasm ko'rigi: Groq modeli %s mos emas (%s)", model, msg[:160])
            unfit += 1
            continue  # bu model yo'q yoki rasm qabul qilmaydi — keyingisi
        logger.warning("Rasm ko'rigi (Groq %s): %s %s", model, r.status_code, msg)
        _fail(f"Groq {r.status_code}: {msg[:140]}")
        # So'rov katta yoki rasmlardan biri yaroqsiz bo'lishi mumkin — bo'lib ko'riladi (model ayblanmaydi).
        return SPLIT if r.status_code in (400, 413, 422) else None
    if models and unfit == len(models):
        if remembered and not fresh:
            cache.delete(_MODEL_KEY.format("groq"))  # eslab qolingan model endi yo'q — ro'yxat yangidan
            return _groq(prompt, images, retried=retried, fresh=True)
        cache.set(_MODEL_KEY.format("groq"), "-", 3600)  # mos model topilmadi — bir soat urinilmaydi
    _fail("Groq'da rasm ko'ra oladigan model topilmadi")
    return None


# --- Gemini ---
def _gemini(prompt: str, images: list[tuple[bytes, str]]):
    # Zaxira: qisqa kutish va qayta urinishsiz — Gemini javob bermasa kartochka daqiqalab kutib qolmasin.
    cfg = {**settings.GEMINI, "TIMEOUT": 15, "RETRY_DELAYS": []}
    parts: list[dict] = [{"text": prompt}]
    for data, mime in images:
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}})
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 600},
    }
    try:
        r = gemini._call_model(cfg["MODEL"], body, cfg)
    except gemini.GeminiError as exc:
        logger.warning("Rasm ko'rigi (Gemini): %s", exc.message)
        cache.set(_COOLDOWN.format("gemini"), True, 900)
        return None
    if r.status_code != 200:
        logger.warning("Rasm ko'rigi (Gemini): %s %s", r.status_code, r.text[:200])
        wait = _wait_seconds(r.text[:300]) if r.status_code == 429 else 900
        cache.set(_COOLDOWN.format("gemini"), True, int(min(max(wait, 60), 6 * 3600)))
        return None
    data = r.json()
    cand = (data.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    try:
        verdicts, notes, kinds = _parse(text, len(images))
    except gemini.GeminiError:
        return None
    meta = data.get("usageMetadata") or {}
    return Result(
        verdicts,
        notes,
        "gemini",
        data.get("modelVersion") or cfg["MODEL"],
        int(meta.get("promptTokenCount") or 0),
        int(meta.get("candidatesTokenCount") or 0),
        kinds,
    )


def verify(label: str, kind: str, shots: list[Shot]) -> Result | None:
    """Har rasm uchun True (shu tovar) / False (boshqa narsa) / None (aniqlanmadi). Xizmat yo'q — None.

    Rasmlar faqat fayl sifatida (kichraytirilgan JPEG) yuboriladi: model saytlardan o'zi yuklay olmasligi
    mumkin. O'qib bo'lmagan rasm tekshirilmaydi (None). Butun tekshiruv BUDGET soniyadan oshmaydi: bepul
    tarifda limit tez tugaydi, kartochka esa kutib qolmasligi kerak.
    """
    if not shots or not settings.AI_CARDS.get("VISION", True):
        return None
    usable = [(i, small) for i, s in enumerate(shots) if (small := _shrink(s))][:MAX_IMAGES]
    if not usable:
        return None
    out = Result([None] * len(shots), [""] * len(shots), kinds=[""] * len(shots))
    kind_text = f" Product type: {kind}." if kind else ""
    deadline = time.monotonic() + BUDGET

    def run(part: list, depth: int) -> bool:
        if time.monotonic() > deadline:
            return False
        prompt = PROMPT.format(label=label, kind=kind_text, n=len(part))
        for p in _providers():
            call = _groq if p == "groq" else _gemini
            res = call(prompt, [small for _, small in part])
            if res == SPLIT:
                # So'rov sig'madi (bepul tarifning daqiqalik token chegarasi) — yarmini yuborib ko'ramiz.
                if len(part) > 1 and depth < 2:
                    mid = (len(part) + 1) // 2
                    first, second = run(part[:mid], depth + 1), run(part[mid:], depth + 1)
                    return first or second
                continue
            if res is not None:
                for j, (i, _) in enumerate(part):
                    if j < len(res.verdicts):
                        out.verdicts[i], out.notes[i] = res.verdicts[j], res.notes[j]
                        out.kinds[i] = res.kinds[j] if j < len(res.kinds) else ""
                out.provider, out.model = res.provider, res.model
                out.tokens_in += res.tokens_in
                out.tokens_out += res.tokens_out
                return True
        return False

    return out if run(usable, 0) else None


def test_png(size: int = 96) -> bytes:
    """Xizmatni tekshirish uchun kichik rasm (bir xil rangli kvadrat)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + b"\x7c\x3a\xed" * size for _ in range(size))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
