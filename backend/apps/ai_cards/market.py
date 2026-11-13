"""Bozor narxi: O'zbekiston do'konlaridagi (.uz) narxlar — bepul qidiruv + sahifa ma'lumoti (schema.org).

AI kaliti/limiti sarflanmaydi. Natija: eng past, o'rtacha (mediana), eng yuqori va tavsiya narx,
manbalari bilan.
Muddatli to'lov ("oyiga", "/мес") narxlari va mantiqsiz qiymatlar tashlanadi.
"""

import hashlib
import re
import statistics
from urllib.parse import urlparse

from django.core.cache import cache

from . import page_hints, research

_PRICE = re.compile(
    r"(\d{1,3}(?:[   .,]\d{3}){1,3})\s*(so['ʻ‘’`]?m|сум|sum|uzs)\b(?=(.{0,18}))",
    re.I,
)
_MONTHLY = re.compile(r"/\s*oy|oyiga|в\s*мес|/\s*мес|ежемес|x\s*\d+|× ?\d+", re.I)
MIN_UZS, MAX_UZS = 50_000, 500_000_000


def prices_in_text(text: str) -> list[int]:
    out = []
    for m in _PRICE.finditer(text or ""):
        if _MONTHLY.search(m.group(3)):
            continue
        value = int(re.sub(r"\D", "", m.group(1)))
        if MIN_UZS <= value <= MAX_UZS:
            out.append(value)
    return out


def _is_uz(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith(".uz") and not any(d in host for d in research.SKIP_DOMAINS)


def market_price(query: str, *, max_pages: int = 5) -> dict:
    query = " ".join(query.split())[:200]
    key = "market_price:" + hashlib.sha256(query.lower().encode()).hexdigest()[:32]
    if (hit := cache.get(key)) is not None:
        return hit
    seen, hits = set(), []
    for q in (f"{query} narxi", f"{query} цена Ташкент"):
        for r in research.web_search(q, max_results=10):
            url = r.get("href") or ""
            if url.startswith("http") and _is_uz(url) and url not in seen:
                seen.add(url)
                hits.append(r)
    sources, fetched = [], 0
    for r in hits:
        found = prices_in_text(f"{r.get('title', '')} {r.get('body', '')}")
        price = min(found) if found else None
        if price is None and fetched < max_pages:
            fetched += 1
            hints = page_hints.fetch(r["href"])
            p, cur = hints.get("price"), hints.get("currency", "")
            if p and cur in ("", "UZS", "SUM", "UZ") and MIN_UZS <= p <= MAX_UZS:
                price = int(p)
        if price:
            sources.append({"url": r["href"], "title": (r.get("title") or "")[:150], "price": price})
    # Bitta do'kon bir nechta sahifa bilan ustunlik qilmasin: domen bo'yicha eng arzon.
    by_host: dict[str, dict] = {}
    for s in sources:
        host = urlparse(s["url"]).netloc.removeprefix("www.")
        if host not in by_host or s["price"] < by_host[host]["price"]:
            by_host[host] = s
    sources = sorted(by_host.values(), key=lambda s: s["price"])
    if sources:
        med = statistics.median(s["price"] for s in sources)
        sources = [s for s in sources if 0.4 * med <= s["price"] <= 2.5 * med]  # aksessuar/xato narxlar
    result = {"query": query, "count": len(sources), "sources": sources}
    if sources:
        values = [s["price"] for s in sources]
        median = int(statistics.median(values))
        result.update(
            min=min(values),
            max=max(values),
            median=median,
            suggested=int(round(median / 10_000) * 10_000),
        )
    cache.set(key, result, 6 * 3600 if sources else 600)
    return result
