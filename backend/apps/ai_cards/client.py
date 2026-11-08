"""Bir nechta AI xizmati: tartib bo'yicha birinchi ulangani ishlatiladi, kvota/limit/xatoda — keyingisi.

Gemini — o'z API'si (Google qidiruvi bilan); qolganlari OpenAI-mos (openai_compat). Kalitlar env/secret'da.
"""

from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings

from . import gemini, openai_compat

AiError = gemini.GeminiError
AiResult = gemini.GeminiResult
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
# Vazifa → xizmatlar tartibi. Bepul tariflilar yuklama bo'yicha almashtiriladi (eng kam ishlatilgani avval).
ROUTES = {
    # Excel/qo'lda: qidiruvni tizim bepul qiladi, bepul AI yozadi; zaxira — qidiruvchi AI'lar.
    "card": [*FREE, "gemini", "perplexity", "deepseek", "yandex", "custom"],
    # Havoladan: Gemini sahifani o'zi o'qiydi (url_context); keyin bepul tadqiqot + bepul AI.
    "url": ["gemini", *FREE, "perplexity", "deepseek", "yandex", "custom"],
    # Rasm: avval AI'siz (qidiruv + sahifa rasmlari); kerak bo'lsa qidiruvchi AI.
    "images": ["perplexity", "gemini", *FREE, "deepseek", "yandex", "custom"],
}
# Bepul tarifdan oshmaslik uchun kunlik so'rov chegarasi (zaxira bilan). Admin: ai_provider_caps.
# Haqiqiy bepul limitlar (2026-11, javob sarlavhalari va xatolardan); bitta kartochka ~6 ming token:
#   Groq gpt-oss-120b: 1000 so'rov/kun, 8000 token/daqiqa, 200 000 token/kun → ~30 kartochka/kun;
#   Cerebras gpt-oss-120b: 5/daqiqa, 150/soat, 2400/kun, 1 mln token/kun → ~150 kartochka/kun;
#   OpenRouter bepul modellar: ~50/kun; Cloudflare: 10 000 neuron/kun.
DEFAULT_CAPS = {
    "groq": 30,
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
    # Bepul tariflilar: eng kam ishlatilgani (limitga nisbatan) birinchi — yuklama taqsimlanadi.
    free = sorted([n for n in route if n in FREE], key=lambda n: used.get(n, 0) / max(limits.get(n, 1), 1))
    it = iter(free)
    route = [next(it) if n in FREE else n for n in route]
    return [by_name[n] for n in route]


def _call(p: Provider, prompt: str, *, url_context: bool, max_tokens: int | None, search: bool) -> AiResult:
    if p.name == "gemini":
        return gemini.generate(prompt, search=search, url_context=url_context, max_tokens=max_tokens)
    return openai_compat.generate(prompt, _config(p.name), max_tokens=max_tokens)


def generate(
    prompt: str | Callable[[bool], str],
    *,
    url_context: bool = False,
    max_tokens: int | None = None,
    search: bool = True,
    task: str = "card",
    **_kw,
) -> AiResult:
    """`prompt` funksiya bo'lsa — xizmatning internet qidiruvi bor-yo'qligiga qarab matn tuziladi."""
    if not active():
        raise AiError("not_configured", "Hech bir AI xizmati ulanmagan: kalitlardan birini kiriting.")
    providers_ = chain(task)
    if not providers_:
        raise AiError("rate_limited", "Barcha AI xizmatlarining bugungi limiti tugadi.")
    failures, last = [], None
    for p in providers_:
        text = prompt(p.search) if callable(prompt) else prompt
        try:
            res = _call(p, text, url_context=url_context, max_tokens=max_tokens, search=search)
        except AiError as exc:
            if exc.code not in SERVICE_ERRORS:
                raise
            failures.append(f"{p.label}: {exc.message}")
            last = exc
            continue
        res.provider = p.name
        if failures:
            res.fallback_notes = failures
        return res
    raise AiError(last.code if last else "unavailable", " | ".join(failures))
