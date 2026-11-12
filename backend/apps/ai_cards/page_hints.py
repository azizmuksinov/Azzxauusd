"""Tovar sahifasidan ochiq ma'lumot: schema.org Product (JSON-LD) va Open Graph teglari.

Faqat yordamchi (eng yaxshi urinish): marketpleyslar botlarni bloklashi mumkin — unda bo'sh natija qaytadi
va kartochkani Gemini o'zi sahifani o'qib (url_context) tuzadi.
"""

import html
import json
import re

import httpx

from apps.core.net import is_public_url, safe_get

from . import gemini

_LD = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
_META = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](og:[a-z:]+|description)["\'][^>]*content=["\']([^"\']*)', re.I
)
_META_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\'](og:[a-z:]+|description)', re.I
)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_PRICE_META = re.compile(
    r'<meta[^>]+(?:property|itemprop|name)=["\'](?:product:price:amount|og:price:amount|price)["\'][^>]*'
    r'content=["\']([\d\s.,]+)',
    re.I,
)


def _products(node):
    if isinstance(node, list):
        for x in node:
            yield from _products(x)
    elif isinstance(node, dict):
        t = node.get("@type")
        if t == "Product" or (isinstance(t, list) and "Product" in t):
            yield node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                yield from _products(node[key])


def _images(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [u for x in value for u in _images(x)]
    if isinstance(value, dict):
        return _images(value.get("url") or value.get("contentUrl"))
    return []


def _price(offers) -> tuple[float | None, str]:
    """schema.org offers (Offer / AggregateOffer / ro'yxat) → (narx, valyuta)."""
    if isinstance(offers, list):
        for o in offers:
            price, cur = _price(o)
            if price:
                return price, cur
        return None, ""
    if not isinstance(offers, dict):
        return None, ""
    for key in ("price", "lowPrice"):
        try:
            v = float(str(offers.get(key, "")).replace(" ", "").replace(",", "."))
        except ValueError:
            continue
        if v > 0:
            return v, str(offers.get("priceCurrency") or "").upper()
    return None, ""


def _specs(props) -> list[dict]:
    """schema.org additionalProperty → [{name, value}] (sahifadagi texnik xususiyatlar)."""
    out = []
    for p in props if isinstance(props, list) else []:
        if isinstance(p, dict) and p.get("name") and p.get("value") not in (None, ""):
            unit = p.get("unitText") or ""
            out.append({"name": str(p["name"])[:120], "value": f"{p['value']} {unit}".strip()[:200]})
    return out[:80]


def parse(page: str) -> dict:
    hints: dict = {}
    for raw in _LD.findall(page):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        for p in _products(data):
            brand = p.get("brand")
            hints.update(
                {
                    "name": p.get("name"),
                    "description": (p.get("description") or "")[:2000],
                    "brand": brand.get("name") if isinstance(brand, dict) else brand,
                    "sku": p.get("sku") or p.get("mpn"),
                    "images": _images(p.get("image"))[:8],
                    "specs": _specs(p.get("additionalProperty")),
                }
            )
            price, currency = _price(p.get("offers"))
            if price:
                hints["price"], hints["currency"] = price, currency
            break
    meta = {k.lower(): html.unescape(v) for k, v in _META.findall(page)}
    meta.update({k.lower(): html.unescape(v) for v, k in _META_REV.findall(page)})
    hints.setdefault("name", meta.get("og:title"))
    if not hints.get("description"):
        hints["description"] = meta.get("og:description") or meta.get("description")
    if not hints.get("images") and meta.get("og:image"):
        hints["images"] = [meta["og:image"]]
    if not hints.get("price") and (m := _PRICE_META.search(page)):
        try:
            hints["price"] = float(m.group(1).replace(" ", "").replace(",", "."))
        except ValueError:
            pass
    if not hints.get("images"):
        # schema.org/og:image yo'q (JavaScript bilan chiziladigan do'konlar) — HTML'dagi birinchi rasmlar
        # (galereya odatda sahifa boshida; pastdagi "o'xshash tovarlar" rasmlari olinmaydi).
        from .images import urls_in_text

        if found := urls_in_text(html.unescape(page.replace("\\u002F", "/").replace("\\/", "/")), limit=6):
            hints["images"] = found
            # Bular sahifaning e'lon qilingan asosiy rasmi emas (logotip, boshqa tovar bo'lishi mumkin):
            # dalil sifatida kuchsizroq hisoblanadi (image_match "page" / "ownpage").
            hints["images_guess"] = True
    if not hints.get("name") and (m := _TITLE.search(page)):
        hints["name"] = html.unescape(m.group(1)).strip()
    return {k: v for k, v in hints.items() if v}


def fetch(url: str) -> dict:
    if not is_public_url(url):
        return {}
    try:
        with gemini.client(timeout=15) as c:
            r = safe_get(
                c,
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
                    "Accept-Language": "uz,ru;q=0.9",
                },
            )
    except httpx.HTTPError:
        return {}
    if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
        return {}
    return parse(r.text[:2_000_000])
