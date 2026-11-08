"""AI provayderini tanlash: settings.AI_CARDS["PROVIDER"] (env AI_PROVIDER) — "gemini" yoki "openai".

Kodning qolgan qismi faqat shu modul orqali ishlaydi — provayder kodni o'zgartirmasdan almashtiriladi.
"""

from django.conf import settings

from . import gemini, openai_compat

AiError = gemini.GeminiError
AiResult = gemini.GeminiResult
SERVICE_ERRORS = gemini.SERVICE_ERRORS
extract_json = gemini.extract_json

_GENERATORS = {"gemini": gemini.generate, "openai": openai_compat.generate}


def provider() -> str:
    return settings.AI_CARDS["PROVIDER"]


def model_name() -> str:
    return settings.GEMINI["MODEL"] if provider() == "gemini" else settings.OPENAI_COMPAT["MODEL"]


def has_search() -> bool:
    """Internet qidiruvi faqat Gemini (Google Search grounding) da."""
    return provider() == "gemini"


def generate(prompt: str, **kw) -> AiResult:
    fn = _GENERATORS.get(provider())
    if fn is None:
        raise AiError("not_configured", f"Noma'lum AI provayder: {provider()}")
    return fn(prompt, **kw)
