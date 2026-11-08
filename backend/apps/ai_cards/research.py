"""Bepul internet tadqiqoti: qidiruv (ddgs, kalitsiz) + sahifani o'qish (schema.org/og + Jina Reader).

Internetdan o'zi qidira olmaydigan arzon/bepul AI'lar (Groq, Cerebras, OpenRouter, DeepSeek...) uchun:
ma'lumotni biz topamiz, AI faqat uni kartochka shakliga keltiradi — qimmat "qidiruv" so'rovlari kerak emas.
Hammasi eng yaxshi urinish: xato bo'lsa bo'sh natija qaytadi.
"""

import logging
from dataclasses import dataclass, field
from urllib.parse import quote, urlparse

import httpx
from django.conf import settings

from . import gemini, page_hints

logger = logging.getLogger(__name__)

# Tovar ma'lumoti kam yoki ishonchsiz bo'lgan saytlar (forum, video, ijtimoiy tarmoq).
SKIP_DOMAINS = ("youtube.", "facebook.", "instagram.", "tiktok.", "vk.com", "t.me", "reddit.", "pinterest.")


@dataclass
class Research:
    sources: list[dict] = field(default_factory=list)  # [{uri, title}]
    pages: list[dict] = field(default_factory=list)  # [{url, title, hints, text}]
    images: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.pages and not self.sources


def web_search(query: str, max_results: int = 8) -> list[dict]:
    """[{title, href, body}] — ddgs (DuckDuckGo, Bing, Brave... metaqidiruv), kalitsiz."""
    try:
        from ddgs import DDGS

        with DDGS(timeout=15) as d:
            return list(d.text(query, max_results=max_results) or [])
    except Exception as exc:  # noqa: BLE001 — tashqi kutubxona turli xato beradi
        logger.warning("Bepul qidiruv xatosi (%s): %s", query, exc)
        return []


def read_page(url: str, limit: int = 6000) -> str:
    """Sahifa matni — Jina Reader (r.jina.ai/<url>); kalitsiz, cheklangan; JINA_API_KEY ixtiyoriy."""
    headers = {"Accept": "text/plain"}
    if key := settings.AI_CARDS.get("JINA_API_KEY"):
        headers["Authorization"] = f"Bearer {key}"
    try:
        with gemini.client(timeout=25, follow_redirects=True) as c:
            r = c.get(f"https://r.jina.ai/{quote(url, safe=':/?&=%#')}", headers=headers)
    except httpx.HTTPError:
        return ""
    return r.text[:limit] if r.status_code == 200 else ""


def collect(query: str, *, brand: str = "", max_pages: int = 3) -> Research:
    out = Research()
    results = [r for r in web_search(query) if r.get("href", "").startswith("http")]
    results = [r for r in results if not any(d in urlparse(r["href"]).netloc for d in SKIP_DOMAINS)]
    # Ishlab chiqaruvchi sayti (domenida brend nomi) — birinchi.
    b = brand.lower().strip()
    results.sort(key=lambda r: 0 if b and b in urlparse(r["href"]).netloc.lower() else 1)
    out.sources = [{"uri": r["href"], "title": r.get("title", "")} for r in results[:8]]
    for r in results[:max_pages]:
        url = r["href"]
        hints = page_hints.fetch(url)
        text = read_page(url) if len(out.pages) < 2 else ""
        out.pages.append(
            {
                "url": url,
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "hints": hints,
                "text": text,
            }
        )
        out.images += [u for u in hints.get("images", []) if isinstance(u, str)]
    out.images = list(dict.fromkeys(out.images))
    return out


def as_prompt(res: Research, limit: int = 12000) -> str:
    if res.empty:
        return "(Internetdan ma'lumot topilmadi.)"
    parts = []
    for p in res.pages:
        block = [f"### {p['title']}\nManba: {p['url']}"]
        if p["snippet"]:
            block.append(p["snippet"])
        if p["hints"]:
            h = {k: v for k, v in p["hints"].items() if k != "images"}
            if h:
                block.append(f"Sahifa ma'lumoti: {h}")
        if p["text"]:
            block.append(p["text"])
        parts.append("\n".join(block))
    return "\n\n".join(parts)[:limit]
