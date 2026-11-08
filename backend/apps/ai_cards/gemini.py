"""Gemini API (generateContent) — Google qidiruvi bilan (grounding).

Hujjat: https://ai.google.dev/api/generate-content
Kalit `x-goog-api-key` sarlavhasida yuboriladi; faqat settings.GEMINI["API_KEY"] dan (env/secret).
"""

import json
import re
from dataclasses import dataclass, field

import httpx
from django.conf import settings

# Testlar uchun: httpx.MockTransport o'rnatiladi.
_transport: httpx.BaseTransport | None = None


class GeminiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class GeminiResult:
    text: str
    sources: list[dict] = field(default_factory=list)
    model: str = ""


def client(**kw) -> httpx.Client:
    return httpx.Client(transport=_transport, **kw)


# Xizmat darajasidagi xatolar: qatorga bog'liq emas — to'ldirish to'xtatiladi, qatorlar navbatda qoladi.
SERVICE_ERRORS = {
    "not_configured",
    "unauthorized",
    "forbidden",
    "model_unavailable",
    "rate_limited",
    "network",
    "unavailable",
}


def generate(prompt: str, *, search: bool = True, max_tokens: int | None = None) -> GeminiResult:
    cfg = settings.GEMINI
    if not cfg["API_KEY"]:
        raise GeminiError("not_configured", "Gemini kaliti sozlanmagan (GEMINI_API_KEY).")
    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    if max_tokens:
        body["generationConfig"]["maxOutputTokens"] = max_tokens
    if search:
        body["tools"] = [{"google_search": {}}]
    url = f"{cfg['BASE_URL'].rstrip('/')}/models/{cfg['MODEL']}:generateContent"
    try:
        with client(timeout=cfg["TIMEOUT"]) as c:
            r = c.post(url, json=body, headers={"x-goog-api-key": cfg["API_KEY"]})
    except httpx.HTTPError as exc:
        raise GeminiError("network", f"Gemini bilan aloqa yo'q: {exc}") from exc
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", "")
        except ValueError:
            msg = r.text[:200]
        code = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "model_unavailable",
            429: "rate_limited",
        }.get(r.status_code, "unavailable" if r.status_code >= 500 else "api_error")
        if code == "bad_request" and "api key" in msg.lower():
            code = "unauthorized"
        raise GeminiError(code, f"Gemini {r.status_code}: {msg}")
    data = r.json()
    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "bo'sh javob")
        raise GeminiError("empty", f"Gemini javob bermadi: {reason}")
    cand = candidates[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    sources = []
    for chunk in (cand.get("groundingMetadata") or {}).get("groundingChunks", []):
        web = chunk.get("web") or {}
        if web.get("uri"):
            sources.append({"uri": web["uri"], "title": web.get("title", "")})
    return GeminiResult(text=text, sources=sources, model=data.get("modelVersion") or cfg["MODEL"])


_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def extract_json(text: str) -> dict:
    """Javob matnidan birinchi JSON obyektni ajratib olish (```json ...``` yoki xom)."""
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text[text.find("{") : text.rfind("}") + 1]
    try:
        value = json.loads(candidate)
    except ValueError as exc:
        raise GeminiError("bad_json", "Gemini javobi JSON emas.") from exc
    if not isinstance(value, dict):
        raise GeminiError("bad_json", "Gemini javobi JSON obyekt emas.")
    return value
