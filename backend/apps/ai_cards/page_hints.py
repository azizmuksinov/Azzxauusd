"""Tovar sahifasidan ochiq ma'lumot: schema.org Product (JSON-LD) va Open Graph teglari.

Faqat yordamchi (eng yaxshi urinish): marketpleyslar botlarni bloklashi mumkin — unda bo'sh natija qaytadi
va kartochkani Gemini o'zi sahifani o'qib (url_context) tuzadi.
"""

import html
import json
import re

import httpx

from . import gemini

_LD = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
_META = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](og:[a-z:]+|description)["\'][^>]*content=["\']([^"\']*)', re.I
)
_META_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\'](og:[a-z:]+|description)', re.I
)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


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
                }
            )
            break
    meta = {k.lower(): html.unescape(v) for k, v in _META.findall(page)}
    meta.update({k.lower(): html.unescape(v) for v, k in _META_REV.findall(page)})
    hints.setdefault("name", meta.get("og:title"))
    if not hints.get("description"):
        hints["description"] = meta.get("og:description") or meta.get("description")
    if not hints.get("images") and meta.get("og:image"):
        hints["images"] = [meta["og:image"]]
    if not hints.get("name") and (m := _TITLE.search(page)):
        hints["name"] = html.unescape(m.group(1)).strip()
    return {k: v for k, v in hints.items() if v}


def fetch(url: str) -> dict:
    try:
        with gemini.client(timeout=15, follow_redirects=True) as c:
            r = c.get(
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
