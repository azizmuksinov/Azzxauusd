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


def _config(name: str) -> dict | None:
    if name == "gemini":
        g = settings.GEMINI
        return {
            "label": "Google Gemini",
            "model": g["MODEL"],
            "search": True,
            "configured": bool(g["API_KEY"]),
        }
    cfg = settings.AI_PROVIDER_CONFIG.get(name)
    if cfg is None:
        return None
    has_key = bool(cfg.get("api_key")) or cfg.get("key_optional", False)
    return {**cfg, "configured": has_key and bool(cfg.get("base_url")) and bool(cfg.get("model"))}


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
            out.append(Provider(name, c["label"], c.get("model", ""), bool(c.get("search")), c["configured"]))
    return out


def active() -> list[Provider]:
    return [p for p in providers() if p.configured]


def provider() -> str:
    a = active()
    return a[0].name if a else ""


def model_name() -> str:
    a = active()
    return a[0].model if a else ""


def has_search() -> bool:
    a = active()
    return a[0].search if a else False


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
    **_kw,
) -> AiResult:
    """`prompt` funksiya bo'lsa — xizmatning internet qidiruvi bor-yo'qligiga qarab matn tuziladi."""
    chain = active()
    if not chain:
        raise AiError("not_configured", "Hech bir AI xizmati ulanmagan: kalitlardan birini kiriting.")
    failures, last = [], None
    for p in chain:
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
