"""Bir nechta AI xizmati: tartib bo'yicha birinchi ulangani ishlatiladi, kvota/limit/xatoda — keyingisi.

Gemini — o'z API'si (Google qidiruvi bilan); qolganlari OpenAI-mos (openai_compat). Kalitlar env/secret'da.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from . import gemini, openai_compat

AiError = gemini.GeminiError
AiResult = gemini.GeminiResult
logger = logging.getLogger(__name__)
SERVICE_ERRORS = gemini.SERVICE_ERRORS
extract_json = gemini.extract_json


@dataclass
class Provider:
    name: str
    label: str
    model: str
    search: bool
    configured: bool
    missing: str = ""  # nima yetishmaydi (kalit, model, hisob raqami)


def _config(name: str) -> dict | None:
    if name == "gemini":
        g = settings.GEMINI
        return {
            "label": "Google Gemini",
            "model": g["MODEL"],
            "search": True,
            "configured": bool(g["API_KEY"]),
            "missing": "" if g["API_KEY"] else "kalit",
        }
    cfg = settings.AI_PROVIDER_CONFIG.get(name)
    if cfg is None:
        return None
    has_key = bool(cfg.get("api_key")) or cfg.get("key_optional", False)
    missing = (
        "kalit"
        if not has_key
        else "manzil (hisob raqami)"
        if not cfg.get("base_url")
        else "model"
        if not cfg.get("model")
        else ""
    )
    return {**cfg, "configured": not missing, "missing": missing}


def order() -> list[str]:
    from apps.core.settings_registry import get_setting

    custom = get_setting("ai_provider_order")
    names = [n.strip() for n in custom.split(",")] if custom else list(settings.AI_CARDS["PROVIDERS"])
    known = ["gemini", *settings.AI_PROVIDER_CONFIG]
    names = [n for n in dict.fromkeys(names) if n in known]
    return names + [n for n in known if n not in names]  # ro'yxatda yo'qlari oxirida (o'chiq emas)


def providers() -> list[Provider]:
    out = []
    for name in order():
        c = _config(name)
        if c:
            out.append(
                Provider(
                    name,
                    c["label"],
                    c.get("model", ""),
                    bool(c.get("search")),
                    c["configured"],
                    c.get("missing", ""),
                )
            )
    return out


def active() -> list[Provider]:
    return [p for p in providers() if p.configured]


def provider(task: str = "card") -> str:
    c = chain(task) if active() else []
    return c[0].name if c else ""


def model_name(task: str = "card") -> str:
    c = chain(task) if active() else []
    return c[0].model if c else ""


def has_search(task: str = "card") -> bool:
    c = chain(task) if active() else []
    return c[0].search if c else False


# --- vazifalar bo'yicha taqsimlash va kunlik limitlar ---
FREE = ("groq", "cerebras", "openrouter", "cloudflare")
# Asosiy xizmat — barcha vazifalarda birinchi (Groq: eng tez, pullik tarifda eng arzon). Qidiruvni tizim
# o'zi bepul qiladi (DuckDuckGo/Bing + Jina), Groq yozadi va tanlaydi. Limiti tugasa (429) — tiklanguncha
# navbatdan chiqadi va zaxiralar ishlaydi (bepullar yuklama bo'yicha, keyin qidiruvchi AI'lar).
PRIMARY = "groq"
ROUTES = {
    "card": [
        PRIMARY,
        "cerebras",
        "openrouter",
        "cloudflare",
        "gemini",
        "perplexity",
        "deepseek",
        "yandex",
        "custom",
    ],
    "url": [
        PRIMARY,
        "cerebras",
        "openrouter",
        "cloudflare",
        "gemini",
        "perplexity",
        "deepseek",
        "yandex",
        "custom",
    ],
    # Rasm: tizim topgan havolalardan aynan shu tovar rasmlarini tanlash (qidiruvsiz AI ham qiladi).
    "images": [
        PRIMARY,
        "cerebras",
        "gemini",
        "perplexity",
        "openrouter",
        "cloudflare",
        "deepseek",
        "yandex",
        "custom",
    ],
}
# Bepul tarifdan oshmaslik uchun kunlik so'rov chegarasi (zaxira bilan). Admin: ai_provider_caps.
# Haqiqiy bepul limitlar (2026-11, javob sarlavhalari va xatolardan); bitta kartochka ~6 ming token:
#   Groq gpt-oss-120b: 1000 so'rov/kun, 8000 token/daqiqa, 200 000 token/kun → ~30 kartochka/kun;
#   Cerebras gpt-oss-120b: 5/daqiqa, 150/soat, 2400/kun, 1 mln token/kun → ~150 kartochka/kun;
#   OpenRouter bepul modellar: ~50/kun; Cloudflare: 10 000 neuron/kun.
DEFAULT_CAPS = {  # Groq'da chegara yo'q: bepul tarifda kunlik token tugasa 429 → tiklanguncha zaxira
    "cerebras": 150,
    "openrouter": 45,
    "cloudflare": 80,
    "gemini": 200,
    "perplexity": 300,
}


def caps() -> dict[str, int]:
    from apps.core.settings_registry import get_setting

    out = dict(DEFAULT_CAPS)
    for part in (get_setting("ai_provider_caps") or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if v.strip().isdigit():
                out[k.strip()] = int(v)
    return out


def used_today() -> dict[str, int]:
    from django.db.models import Count
    from django.utils import timezone

    from .models import AiCall

    rows = (
        AiCall.objects.filter(created_at__date=timezone.localdate())
        .values("provider")
        .annotate(n=Count("id"))
    )
    return {r["provider"]: r["n"] for r in rows}


def chain(task: str = "card") -> list[Provider]:
    """Vazifa uchun tartib: admin tartibi (ai_provider_order) yoki ROUTES; limiti tugaganlar tashlanadi."""
    from apps.core.settings_registry import get_setting

    by_name = {p.name: p for p in active()}
    route = list(by_name) if get_setting("ai_provider_order") else ROUTES.get(task, ROUTES["card"])
    route = [n for n in route if n in by_name] + [n for n in by_name if n not in route]
    limits, used = caps(), used_today()
    route = [n for n in route if n not in limits or used.get(n, 0) < limits[n]]
    route = [n for n in route if not cache.get(_COOLDOWN.format(n))]  # limiti tugab, kutish vaqtidagilar
    budget = get_setting("ai_daily_budget_usd")
    if budget is not None:  # kunlik dollar chegarasi: narxi ma'lum (pullik) xizmat to'xtaydi, bepullar qoladi
        spent = cost_today()
        route = [n for n in route if n not in PRICES or spent.get(n, 0) < float(budget)]
    # Zaxira bepul tariflilar: eng kam ishlatilgani (limitga nisbatan) birinchi; asosiy xizmat joyida qoladi.
    free = sorted(
        [n for n in route if n in FREE and n != PRIMARY],
        key=lambda n: used.get(n, 0) / max(limits.get(n, 1), 1),
    )
    it = iter(free)
    route = [next(it) if n in FREE and n != PRIMARY else n for n in route]
    return [by_name[n] for n in route]


# Narx (USD, 1 mln token: kiruvchi, chiquvchi) — xarajat hisobi uchun (2026-11). Bepul tarifda haqiqiy to'lov
# yo'q, raqam "pullik tarifda qancha bo'lardi" ni ko'rsatadi.
PRICES = {"groq": (0.15, 0.60)}


def tokens_today() -> dict[str, tuple[int, int]]:
    from django.db.models import Sum
    from django.utils import timezone

    from .models import AiCall

    rows = (
        AiCall.objects.filter(created_at__date=timezone.localdate())
        .values("provider")
        .annotate(i=Sum("tokens_in"), o=Sum("tokens_out"))
    )
    return {r["provider"]: (r["i"] or 0, r["o"] or 0) for r in rows}


def cost_today() -> dict[str, float]:
    out = {}
    for name, (i, o) in tokens_today().items():
        if name in PRICES:
            pin, pout = PRICES[name]
            out[name] = round(i / 1e6 * pin + o / 1e6 * pout, 4)
    return out


def _call(p: Provider, prompt: str, *, url_context: bool, max_tokens: int | None, search: bool) -> AiResult:
    if p.name == "gemini":
        return gemini.generate(prompt, search=search, url_context=url_context, max_tokens=max_tokens)
    return openai_compat.generate(prompt, _config(p.name), max_tokens=max_tokens)


_COOLDOWN = "ai_cooldown:{}"


def cooldown_seconds(message: str) -> int:
    """429 xabaridagi kutish vaqti ("try again in 26m17.6s", "retry after 30s"); topilmasa — 1 daqiqa.

    Limiti tugagan xizmat shu vaqtgacha navbatdan chiqariladi — har kartochkada behuda urinish bo'lmaydi.
    """
    m = re.search(
        r"(?:try again in|retry after)\s*(?:(\d+)h)?\s*(?:(\d+)m(?!s))?\s*(?:([\d.]+)s)?", message, re.I
    )
    if not m or not any(m.groups()):
        return 60  # daqiqalik limitlar (masalan Gemini RPM) — tez tiklanadi
    h, mi, s = (float(x) if x else 0 for x in m.groups())
    return int(min(max(h * 3600 + mi * 60 + s, 60), 6 * 3600))


def generate(
    prompt: str | Callable[[bool], str],
    *,
    url_context: bool = False,
    max_tokens: int | None = None,
    search: bool = True,
    task: str = "card",
    expect_json: bool = False,
    **_kw,
) -> AiResult:
    """`prompt` funksiya bo'lsa — xizmatning internet qidiruvi bor-yo'qligiga qarab matn tuziladi.

    expect_json: javob JSON bo'lmasa (model ba'zan oddiy matn yozadi) — keyingi xizmatga o'tiladi.
    """
    if not active():
        raise AiError("not_configured", "Hech bir AI xizmati ulanmagan: kalitlardan birini kiriting.")
    providers_ = chain(task)
    if not providers_:
        raise AiError("rate_limited", "Barcha AI xizmatlarining bugungi limiti tugadi.")
    failures, last = [], None
    for p in providers_:
        text = prompt(p.search) if callable(prompt) else prompt
        if text is None:  # bu vazifa uchun internet qidiruvi kerak, xizmat esa qidira olmaydi
            failures.append(f"{p.label}: internetdan qidira olmaydi")
            continue
        try:
            res = _call(p, text, url_context=url_context, max_tokens=max_tokens, search=search)
        except AiError as exc:
            if exc.code not in SERVICE_ERRORS:
                raise
            failures.append(f"{p.label}: {exc.message}")
            last = exc
            if exc.code == "rate_limited":
                cache.set(_COOLDOWN.format(p.name), True, cooldown_seconds(exc.message))
            continue
        res.provider = p.name
        if expect_json:
            try:
                extract_json(res.text)
            except AiError as exc:
                logger.warning("%s javobi JSON emas: %r", p.name, (res.text or "")[:300])
                failures.append(f"{p.label}: javobi JSON emas")
                last = exc
                continue
        if failures:
            res.fallback_notes = failures
        return res
    raise AiError(last.code if last else "unavailable", " | ".join(failures))
