"""OpenAI-mos chat completions: Perplexity, DeepSeek, YandexGPT, OpenRouter, Groq, Ollama/vLLM.

`POST {base_url}/chat/completions`, `Authorization: Bearer {api_key}` (+ qo'shimcha sarlavhalar,
masalan Yandex uchun `OpenAI-Project: <folder_id>`). Internetdan qidirish faqat Perplexity'da
(javobdagi manbalar olinadi).
"""

import httpx

from .gemini import GeminiError, GeminiResult, client


def _responses(
    prompt: str, cfg: dict, headers: dict, *, max_tokens: int | None, timeout: int
) -> httpx.Response:
    """Responses/Agent API (Perplexity): input — matn, web_search vositasi bilan."""
    url = f"{cfg['base_url'].rstrip('/')}/v1/responses"
    body: dict = {"model": cfg["model"], "input": prompt, "tools": [{"type": "web_search"}]}
    if max_tokens:
        body["max_output_tokens"] = max_tokens
    with client(timeout=timeout) as c:
        r = c.post(url, json=body, headers=headers)
        if r.status_code == 400 and "tool" in r.text.lower():
            body.pop("tools")
            r = c.post(url, json=body, headers=headers)
    return r


def _parse_responses(data: dict) -> tuple[str, list[dict]]:
    text = data.get("output_text") or ""
    sources: list[dict] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message" and not text:
            text = "".join(c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict))
        for res in item.get("results") or []:
            if isinstance(res, dict) and res.get("url"):
                sources.append({"uri": res["url"], "title": res.get("title", "")})
    return text, sources


def generate(prompt: str, cfg: dict, *, max_tokens: int | None = None, timeout: int = 120) -> GeminiResult:
    if not cfg.get("base_url") or not cfg.get("model"):
        raise GeminiError("not_configured", f"{cfg.get('label', 'AI')} sozlanmagan (manzil yoki model yo'q).")
    body: dict = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    if max_tokens:
        body["max_tokens"] = max_tokens
    headers = dict(cfg.get("headers") or {})
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    label = cfg.get("label", "AI")
    try:
        if cfg.get("api") == "responses":
            r = _responses(prompt, cfg, headers, max_tokens=max_tokens, timeout=timeout)
        else:
            with client(timeout=timeout) as c:
                r = c.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise GeminiError("network", f"{label} bilan aloqa yo'q ({type(exc).__name__}): {exc}") from exc
    if r.status_code != 200:
        try:
            err = r.json().get("error", {})
            msg = err.get("message", "") if isinstance(err, dict) else str(err)
        except ValueError:
            msg = r.text[:200]
        code = {
            401: "unauthorized",
            402: "rate_limited",  # balans tugagan (DeepSeek, OpenRouter)
            403: "forbidden",
            404: "model_unavailable",
            429: "rate_limited",
        }.get(r.status_code, "unavailable" if r.status_code >= 500 else "bad_request")
        raise GeminiError(code, f"{label} {r.status_code}: {msg}")
    data = r.json()
    limits = {k.lower(): v for k, v in r.headers.items() if "ratelimit" in k.lower()}
    if cfg.get("api") == "responses":
        text, sources = _parse_responses(data)
        if not text:
            raise GeminiError("empty", f"{label} javob bermadi.")
        return GeminiResult(
            text=text, sources=sources, model=data.get("model") or cfg["model"], limits=limits
        )
    choices = data.get("choices") or []
    if not choices:
        raise GeminiError("empty", f"{label} javob bermadi.")
    text = (choices[0].get("message") or {}).get("content") or ""
    sources = [
        {"uri": s.get("url", ""), "title": s.get("title", "")}
        for s in data.get("search_results") or []
        if isinstance(s, dict) and s.get("url")
    ] or [{"uri": u, "title": ""} for u in data.get("citations") or [] if isinstance(u, str)]
    return GeminiResult(text=text, sources=sources, model=data.get("model") or cfg["model"], limits=limits)
