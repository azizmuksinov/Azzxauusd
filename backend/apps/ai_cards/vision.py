"""Ko'ruvchi AI: tanlangan rasmlarda haqiqatan shu tovar tasvirlanganini tekshirish.

Matn bo'yicha dalillar (image_match) "bu rasm shu model sahifasidan" deydi, lekin rasmda nima borligini
ko'rmaydi: banner, o'lcham jadvali, aksessuar yoki umuman boshqa tovar bo'lishi mumkin. Shu modul rasmlarni
ko'ra oladigan modelga (Groq'dagi vision modeli, zaxirada Gemini) yuboradi va har biriga "ha/yo'q" oladi.

Hammasi eng yaxshi urinish: xizmat ishlamasa yoki limiti tugasa — None qaytadi va chaqiruvchi faqat
ishonchli (dalilli) rasmlarni qoldiradi.
"""

import base64
import logging
import re
import struct
import zlib
from dataclasses import dataclass, field

import httpx
from django.conf import settings
from django.core.cache import cache

from . import gemini

logger = logging.getLogger(__name__)

MAX_IMAGES = 5  # bitta so'rovda
INLINE_MAX = 1_200_000  # bayt: bundan katta rasm havola bilan yuboriladi
INLINE_TOTAL = 3_000_000
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
Reply with JSON only: {{"images":[{{"n":1,"verdict":"ok","what":"short description, 3-6 words"}}]}}"""


@dataclass
class Result:
    verdicts: list[bool | None]
    notes: list[str] = field(default_factory=list)  # har rasmda nima ko'rindi (qisqa)
    provider: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class Shot:
    url: str
    content: bytes = b""
    ext: str = ""


def enabled() -> bool:
    return bool(settings.AI_CARDS.get("VISION", True)) and bool(_providers())


def _providers() -> list[str]:
    out = []
    if (settings.AI_PROVIDER_CONFIG.get("groq") or {}).get("api_key"):
        out.append("groq")
    if settings.GEMINI.get("API_KEY"):
        out.append("gemini")
    return [p for p in out if not cache.get(_COOLDOWN.format(p))]


def _parse(text: str, n: int) -> tuple[list[bool | None], list[str]]:
    data = gemini.extract_json(text)
    verdicts: list[bool | None] = [None] * n
    notes = [""] * n
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
    return verdicts, notes


def _usable(shots: list[Shot]) -> list[int]:
    """Modelga yuborsa bo'ladigan rasmlar (AVIF/HEIC ko'p modelda ochilmaydi)."""
    return [i for i, s in enumerate(shots) if s.ext in MIME or not s.content]


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


def _groq(prompt: str, shots: list[Shot], *, inline: bool = True) -> Result | None:
    from .client import cooldown_seconds

    cfg = settings.AI_PROVIDER_CONFIG["groq"]
    content: list[dict] = [{"type": "text", "text": prompt}]
    total = 0
    for s in shots:
        url = s.url
        if inline and s.content and len(s.content) <= INLINE_MAX and total + len(s.content) <= INLINE_TOTAL:
            total += len(s.content)
            url = f"data:{MIME[s.ext]};base64,{base64.b64encode(s.content).decode()}"
        content.append({"type": "image_url", "image_url": {"url": url}})
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    models = _groq_models(cfg)
    for model in models:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": 500,
        }
        try:
            with gemini.client(timeout=90) as c:
                r = c.post(f"{cfg['base_url'].rstrip('/')}/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("Rasm ko'rigi (Groq %s): aloqa yo'q — %s", model, exc)
            return None
        if r.status_code == 200:
            data = r.json()
            text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            u = data.get("usage") or {}
            try:
                verdicts, notes = _parse(text, len(shots))
            except gemini.GeminiError:
                logger.warning("Rasm ko'rigi (Groq %s): javob JSON emas: %r", model, text[:200])
                return None
            cache.set(_MODEL_KEY.format("groq"), model, 6 * 3600)
            return Result(
                verdicts,
                notes,
                "groq",
                data.get("model") or model,
                int(u.get("prompt_tokens") or 0),
                int(u.get("completion_tokens") or 0),
            )
        msg = r.text[:300]
        if r.status_code == 429:
            cache.set(_COOLDOWN.format("groq"), True, cooldown_seconds(msg))
            return None
        too_big = r.status_code == 413 or bool(re.search(r"too large|too big|size|base64", msg, re.I))
        if inline and total and too_big:
            return _groq(prompt, shots, inline=False)  # rasm hajmi sig'madi — havolalar bilan
        if r.status_code in (400, 404):
            logger.info("Rasm ko'rigi: Groq modeli %s mos emas (%s)", model, msg[:160])
            continue  # bu model yo'q yoki rasm qabul qilmaydi — keyingisi
        logger.warning("Rasm ko'rigi (Groq %s): %s %s", model, r.status_code, msg)
        return None
    if models:
        cache.set(_MODEL_KEY.format("groq"), "-", 3600)  # mos model topilmadi — bir soat urinilmaydi
    return None


# --- Gemini ---
def _gemini(prompt: str, shots: list[Shot]) -> Result | None:
    from .client import cooldown_seconds

    cfg = settings.GEMINI
    parts: list[dict] = [{"text": prompt}]
    sent = 0
    for s in shots:
        if not s.content or s.ext not in MIME or sent + len(s.content) > 12_000_000:
            return None  # Gemini'ga rasm faqat fayl sifatida yuboriladi
        sent += len(s.content)
        parts.append(
            {"inline_data": {"mime_type": MIME[s.ext], "data": base64.b64encode(s.content).decode()}}
        )
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 600},
    }
    try:
        r = gemini._call_model(cfg["MODEL"], body, cfg)
    except gemini.GeminiError as exc:
        logger.warning("Rasm ko'rigi (Gemini): %s", exc.message)
        return None
    if r.status_code == 429:
        cache.set(_COOLDOWN.format("gemini"), True, cooldown_seconds(r.text[:300]))
        return None
    if r.status_code != 200:
        logger.warning("Rasm ko'rigi (Gemini): %s %s", r.status_code, r.text[:200])
        return None
    data = r.json()
    cand = (data.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    try:
        verdicts, notes = _parse(text, len(shots))
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
    )


def verify(label: str, kind: str, shots: list[Shot]) -> Result | None:
    """Har rasm uchun True (shu tovar) / False (boshqa narsa) / None (aniqlanmadi). Xizmat yo'q — None."""
    if not shots or not settings.AI_CARDS.get("VISION", True):
        return None
    idx = _usable(shots)[:MAX_IMAGES]
    if not idx:
        return None
    subset = [shots[i] for i in idx]
    prompt = PROMPT.format(label=label, kind=f" Product type: {kind}." if kind else "", n=len(subset))
    res = None
    for p in _providers():
        res = _groq(prompt, subset) if p == "groq" else _gemini(prompt, subset)
        if res is not None:
            break
    if res is None:
        return None
    verdicts: list[bool | None] = [None] * len(shots)
    notes = [""] * len(shots)
    for j, i in enumerate(idx):
        verdicts[i], notes[i] = res.verdicts[j], res.notes[j]
    res.verdicts, res.notes = verdicts, notes
    return res


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
