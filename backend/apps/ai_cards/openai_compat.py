"""OpenAI-mos chat completions API: OpenRouter, Groq, Together, o'z serverdagi Ollama / vLLM / LM Studio.

`POST {AI_BASE_URL}/chat/completions`, `Authorization: Bearer {AI_API_KEY}` (lokal serverda kalit shart emas).
Internet qidiruvi yo'q — model o'z bilimidan foydalanadi; rasm havolalari tekshiriladi,
ochilmaganlari tashlanadi.
"""

import httpx
from django.conf import settings

from .gemini import GeminiError, GeminiResult, client


def generate(prompt: str, *, search: bool = True, max_tokens: int | None = None, **_kw) -> GeminiResult:
    cfg = settings.OPENAI_COMPAT
    if not cfg["BASE_URL"] or not cfg["MODEL"]:
        raise GeminiError("not_configured", "AI sozlanmagan (AI_BASE_URL va AI_MODEL).")
    body: dict = {
        "model": cfg["MODEL"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    if max_tokens:
        body["max_tokens"] = max_tokens
    headers = {"Authorization": f"Bearer {cfg['API_KEY']}"} if cfg["API_KEY"] else {}
    url = f"{cfg['BASE_URL'].rstrip('/')}/chat/completions"
    try:
        with client(timeout=cfg["TIMEOUT"]) as c:
            r = c.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise GeminiError("network", f"AI bilan aloqa yo'q: {exc}") from exc
    if r.status_code != 200:
        try:
            err = r.json().get("error", {})
            msg = err.get("message", "") if isinstance(err, dict) else str(err)
        except ValueError:
            msg = r.text[:200]
        code = {401: "unauthorized", 403: "forbidden", 404: "model_unavailable", 429: "rate_limited"}.get(
            r.status_code, "unavailable" if r.status_code >= 500 else "bad_request"
        )
        raise GeminiError(code, f"AI {r.status_code}: {msg}")
    data = r.json()
    choices = data.get("choices") or []
    if not choices:
        raise GeminiError("empty", "AI javob bermadi.")
    text = (choices[0].get("message") or {}).get("content") or ""
    return GeminiResult(text=text, sources=[], model=data.get("model") or cfg["MODEL"])
