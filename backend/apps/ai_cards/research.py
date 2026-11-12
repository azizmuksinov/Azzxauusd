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
    # Rasm nomzodlari manbasi bilan: [{url, origin: "main"|"page", page, title, alt}] — image_match uchun.
    candidates: list[dict] = field(default_factory=list)

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


def _key(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def image_search(
    query: str, model_code: str = "", max_results: int = 25, min_side: int = 500, brand: str = ""
) -> list[str]:
    """Katta rasmlar havolalari — ddgs rasm qidiruvi (kalitsiz).

    Faqat sarlavhasi yoki havolasida model kodi bor rasmlar (boshqa tovar, logotip emas); kattasi oldin.
    Qisqa kod (H1c, C6N...) — brend ham yozilgan bo'lishi shart. Model kodi bo'lmasa — bo'sh ro'yxat.
    """
    code, brand_key = _key(model_code), _key(brand)
    if len(code) < 2 or (len(code) < 4 and len(brand_key) < 2):
        return []
    try:
        from ddgs import DDGS

        with DDGS(timeout=15) as d:
            items = list(d.images(query, max_results=max_results) or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rasm qidiruvi xatosi (%s): %s", query, exc)
        return []
    good = []
    for it in items:
        url = it.get("image")
        try:
            w, h = int(it.get("width") or 0), int(it.get("height") or 0)
        except (TypeError, ValueError):
            w = h = 0
        # O'lcham noma'lum (Bing ko'pincha bermaydi) — qoldiriladi; haqiqiy o'lcham yuklashda tekshiriladi.
        if not (isinstance(url, str) and url.startswith("http")) or (w and h and min(w, h) < min_side):
            continue
        if any(d in urlparse(url).netloc for d in SKIP_DOMAINS) or "logo" in url.lower():
            continue
        hay = _key(f"{it.get('title', '')} {url} {it.get('url', '')}")
        if code not in hay or (len(code) < 4 and brand_key not in hay):
            continue
        good.append((w * h, url))
    logger.info(
        "Rasm qidiruvi %r: %s ta natija, %s tasi mos; namuna: %s",
        query,
        len(items),
        len(good),
        [
            (it.get("title", "")[:60], it.get("width"), it.get("height"), str(it.get("image", ""))[:80])
            for it in items[:3]
        ],
    )
    return [u for _, u in sorted(good, reverse=True)]


def read_page(url: str, limit: int = 6000) -> str:
    """Sahifa matni — Jina Reader (r.jina.ai/<url>); kalitsiz, cheklangan; JINA_API_KEY ixtiyoriy."""
    return read_page_full(url, limit)[0]


def read_page_full(url: str, limit: int = 6000) -> tuple[str, list[str]]:
    """(matn, rasm havolalari). Jina sahifani brauzerda ochadi — JavaScript bilan chiziladigan do'konlar
    (Uzum va h.k.) rasmlari ham shu yerda; rasm ro'yxati butun matndan (qisqartirishdan oldin) olinadi."""
    from . import images

    headers = {"Accept": "text/plain", "X-With-Images-Summary": "true"}
    if key := settings.AI_CARDS.get("JINA_API_KEY"):
        headers["Authorization"] = f"Bearer {key}"
    try:
        with gemini.client(timeout=30, follow_redirects=True) as c:
            r = c.get(f"https://r.jina.ai/{quote(url, safe=':/?&=%#')}", headers=headers)
    except httpx.HTTPError:
        return "", []
    if r.status_code != 200:
        return "", []
    return r.text[:limit], images.urls_in_text(r.text)


RESEARCH_TTL = 7 * 24 * 3600


def collect(
    query: str,
    *,
    brand: str = "",
    max_pages: int = 3,
    queries: list[str] | None = None,
    code: str = "",
) -> Research:
    """Qidiruv + sahifalar (7 kun keshda: qayta yaratish/avto-tuzatishda internet qayta qidirilmaydi).

    `queries` — tayyor so'rovlar (smart.understand tozalagan); bo'lmasa — `query` va "<query> характеристики".
    `code` — model kodi / artikul: aynan shu kod yozilgan sahifalar birinchi o'qiladi.
    """
    import hashlib

    from django.core.cache import cache

    queries = [q for q in (queries or [query, f"{query} характеристики"]) if q.strip()]
    raw_key = "|".join([*queries, brand, str(max_pages), code]).lower()
    key = "research:" + hashlib.sha256(raw_key.encode()).hexdigest()[:32]
    if (hit := cache.get(key)) is not None:
        return hit
    res = _collect(queries, brand=brand, max_pages=max_pages, code=code)
    if not res.empty:
        cache.set(key, res, RESEARCH_TTL)
    return res


def _collect(queries: list[str], *, brand: str = "", max_pages: int = 3, code: str = "") -> Research:
    out = Research()
    # Ikki so'rov: model nomi va "характеристики" (xususiyatlar sahifalari ko'proq chiqadi).
    seen, merged = set(), []
    for q in queries:
        for r in web_search(q):
            if r.get("href") and r["href"] not in seen:
                seen.add(r["href"])
                merged.append(r)
    from . import image_match

    b, ck = brand.lower().strip(), _key(code)
    target = image_match.Target(brand=brand, code=code) if len(ck) >= 4 else None

    def level(r: dict) -> int:
        """Sahifa shu model haqidami: 2 — aynan shu kod; 1 — shu model/seriya (kod oxiridagi rang yoki
        bozor harfisiz: "PRM-GE6031MD" — biznikisi PRM-GE6031MD-S); 0 — yo'q."""
        return image_match.page_level(target, r.get("title", ""), r["href"]) if target else 0

    def clean(items: list[dict]) -> list[dict]:
        items = [r for r in items if r.get("href", "").startswith("http")]
        return [r for r in items if not any(d in urlparse(r["href"]).netloc for d in SKIP_DOMAINS)]

    results = clean(merged)
    if target and not any(level(r) == 2 for r in results):
        # Aynan shu kod yozilgan sahifa chiqmadi — aniqroq so'rovlar: kod qo'shtirnoqda, keyin ishlab
        # chiqaruvchi saytining o'zidan (qidiruvda uning boshqa sahifalari chiqqan bo'lsa).
        extra = [f'"{code}"']
        maker = next(
            (urlparse(r["href"]).netloc for r in results if b and b in urlparse(r["href"]).netloc), ""
        )
        if maker:
            extra.append(f"site:{maker} {code}")
        for q in extra:
            for r in clean(web_search(q)):
                if r["href"] not in seen:
                    seen.add(r["href"])
                    results.append(r)

    def about(r: dict) -> str:
        return f"{r.get('title', '')} {r['href']} {r.get('body', '')}"

    if b or target:
        # Tovarga aloqasi yo'q natijalar (kam uchraydigan kodda qidiruv tasodifiy saytlarni ham beradi):
        # na brend, na kod tilga olinmagan sahifa o'qilmaydi va manba sifatida ko'rsatilmaydi.
        results = [
            r
            for r in results
            if (b and b in about(r).lower()) or (target and ck in _key(about(r))) or level(r)
        ]

    def rank(r: dict) -> tuple:
        url = r["href"].lower()
        service = any(x in url for x in ("/support", "download", "driver", "manual", "/parts", "helpdesk"))
        maker = bool(b) and b in urlparse(url).netloc
        # Aynan shu kod yozilgan sahifa birinchi, keyin shu model (kodi qisqa yozilgan); drayver/yordam
        # sahifalari oxirida; tengida — rasmiy sayt oldin.
        return (-level(r), service, not maker)

    results.sort(key=rank)
    out.sources = [{"uri": r["href"], "title": r.get("title", "")} for r in results[:8]]
    for r in results[:max_pages]:
        url = r["href"]
        hints = page_hints.fetch(url)
        text, page_imgs = read_page_full(url, limit=4500) if len(out.pages) < 3 else ("", [])
        out.pages.append(
            {
                "url": url,
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "hints": hints,
                "text": text,
                # 2 — aynan shu kod; 1 — shu model (kodi rang/bozor qo'shimchasisiz yozilgan); 0 — noma'lum.
                "level": level(r),
            }
        )
        out.candidates += page_candidates(url, r.get("title", ""), hints, page_imgs)
    out.images = list(dict.fromkeys(c["url"] for c in out.candidates))
    return out


def page_candidates(url: str, title: str, hints: dict, page_imgs: list, limit: int = 12) -> list[dict]:
    """Bitta sahifaning rasm nomzodlari: asosiy rasmlar (schema.org / og:image) va sahifa ichidagilar."""
    full_title = " ".join(str(x) for x in (title, hints.get("name"), hints.get("sku")) if x)
    main_origin = "page" if hints.get("images_guess") else "main"
    out = [
        {"url": str(u), "origin": main_origin, "page": url, "title": full_title, "alt": getattr(u, "alt", "")}
        for u in hints.get("images", [])
        if isinstance(u, str)
    ]
    out += [
        {"url": str(u), "origin": "page", "page": url, "title": full_title, "alt": getattr(u, "alt", "")}
        for u in page_imgs[:limit]
        if isinstance(u, str)
    ]
    return out


# Tizim sahifani "aynan shu model haqida" deb aniqlaganida sarlavhaga qo'yiladigan belgi (AI uchun).
SAME_MODEL = "[SHU MODEL SAHIFASI]"


def as_prompt(res: Research, limit: int = 9000) -> str:
    if res.empty:
        return "(Internetdan ma'lumot topilmadi.)"
    parts = []
    for p in res.pages:
        mark = {2: " " + SAME_MODEL, 1: " " + SAME_MODEL}.get(p.get("level", 0), "")
        block = [f"### {p['title']}{mark}\nManba: {p['url']}"]
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
