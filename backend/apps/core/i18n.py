"""Ko'p tilli JSON maydonlar bilan ishlash: {"uz": ..., "uz_cyrl": ..., "ru": ...}."""

from .translit import latin_to_cyrillic

LANG_KEYS = ("uz", "uz_cyrl", "ru")


def lang_key(language_code: str | None) -> str:
    code = (language_code or "uz").lower().replace("-", "_")
    if code.startswith("ru"):
        return "ru"
    if code.startswith("uz_cyrl"):
        return "uz_cyrl"
    return "uz"


def localize(value: dict | None, language_code: str | None) -> str:
    """Kerakli tildagi qiymat; bo'lmasa - mantiqiy zaxira variant."""
    if not value:
        return ""
    key = lang_key(language_code)
    if value.get(key):
        return value[key]
    if key == "uz_cyrl" and value.get("uz"):
        return latin_to_cyrillic(value["uz"])
    return value.get("uz") or value.get("ru") or ""


def request_language(request) -> str:
    """So'rov tili: ?lang= yoki Accept-Language (birinchi qiymat). Natija: uz | uz_cyrl | ru."""
    if request is None:
        return "uz"
    lang = request.query_params.get("lang") if hasattr(request, "query_params") else None
    if not lang:
        header = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
        lang = header.split(",")[0].split(";")[0].strip()
    return lang_key(lang)
