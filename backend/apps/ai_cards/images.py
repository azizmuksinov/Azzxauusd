"""Rasmlarni ishonchli yuklash: turi fayl boshidan aniqlanadi (CDN'lar ko'pincha `application/octet-stream`
yuboradi), yuklanmasa boshqa sarlavhalar bilan qayta uriniladi (hotlink himoyasi), eskiz havolasidan kattasi
sinab ko'riladi, sahifa matnidagi rasm havolalari ham olinadi.
"""

import re
import struct
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from django.conf import settings

from . import gemini

MIN_SIDE = 300  # px — bundan kichigi eskiz (64x64, 45x45 ...)
UNKNOWN_SIZE_MIN_BYTES = 15_000  # o'lchami o'qilmagan rasm shundan katta bo'lsa — qabul
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)


def sniff(data: bytes) -> str | None:
    """Fayl boshidagi belgilar bo'yicha rasm turi (kengaytma) yoki None (HTML, matn va h.k.)."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"avif", b"avis"):
            return "avif"
        if brand in (b"heic", b"heix", b"mif1", b"msf1"):
            return "heic"
    if data[:2] == b"BM":
        return "bmp"
    return None


def image_size(data: bytes) -> tuple[int, int] | None:
    """PNG/JPEG/GIF/WEBP/AVIF/HEIC sarlavhasidan o'lcham (kutubxonasiz). Aniqlanmasa — None."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", data[6:10])
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            if data[12:16] == b"VP8X":
                return (int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1)
            if data[12:16] == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if data[12:16] == b"VP8L":
                b = data[21:25]
                w = 1 + (((b[1] & 0x3F) << 8) | b[0])
                h = 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
                return w, h
        if data[4:8] == b"ftyp":  # AVIF/HEIC: 'ispe' qutisida kenglik va balandlik
            i = data.find(b"ispe", 0, 4096)
            if i > 0:
                return struct.unpack(">II", data[i + 8 : i + 16])
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                    return w, h
                i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]
    except (struct.error, IndexError):
        return None
    return None


@dataclass
class Fetched:
    url: str
    ok: bool
    content: bytes = b""
    ext: str = ""
    size: tuple[int, int] | None = None
    reason: str = ""

    @property
    def area(self) -> int:
        return self.size[0] * self.size[1] if self.size else 0


def bigger_variants(url: str) -> list[str]:
    """Eskiz havolasidan kattaroq variantlar (ma'lum CDN'lar, umumiy WxH naqshlari); ishlashi tekshiriladi."""
    out = []
    # Uzum: .../t_product_540_high.jpg → t_product_high (katta)
    if "images.uzum.uz" in url:
        out += [
            re.sub(r"t_product_\d+_(high|low)", "t_product_high", url),
            re.sub(r"/t_[^/]+\.jpg", "/original.jpg", url),
        ]
    # DNS: /thumb/st1/fit/64/64/<hash>/<file> → katta o'lcham
    out.append(re.sub(r"/thumb/st\d/fit/\d+/\d+/", "/thumb/st1/fit/1200/1200/", url))
    # umumiy: /200x200/, _200x200., -150x150.jpg, ?w=200, width=200
    out.append(re.sub(r"([/_-])\d{2,3}x\d{2,3}([/._-])", r"\g<1>1200x1200\g<2>", url))
    out.append(re.sub(r"([?&](?:w|width|size)=)\d{2,3}\b", r"\g<1>1200", url))
    return [u for u in dict.fromkeys(out) if u != url]


def fetch(url: str, *, referer: str = "", timeout: int = 15) -> Fetched:
    """Rasmni yuklash: turli sarlavhalar bilan (bot/brauzer, referer) qayta urinib; sababi o'zbekcha."""
    if urlparse(url).scheme not in ("http", "https"):
        return Fetched(url, False, reason="havola noto'g'ri")
    origin = "{0.scheme}://{0.netloc}/".format(urlparse(url))
    attempts = [
        {
            "User-Agent": BROWSER_UA,
            "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
            "Referer": referer or origin,
        },
        {"User-Agent": BROWSER_UA, "Accept": "image/*,*/*"},
        {"User-Agent": "Mozilla/5.0 (catalog image check)"},
    ]
    limit = settings.AI_CARDS["IMAGE_MAX_BYTES"]
    reason = "ochilmadi"
    with gemini.client(timeout=timeout, follow_redirects=True) as c:
        for headers in attempts:
            try:
                r = c.get(url, headers=headers)
            except httpx.HTTPError:
                reason = "ochilmadi (tarmoq)"
                continue
            if r.status_code != 200:
                reason = f"server javobi {r.status_code}"
                continue
            ext = sniff(r.content[:64])
            if ext is None:
                reason = "rasm emas (sahifa yoki matn qaytdi)"
                continue
            if len(r.content) > limit:
                return Fetched(url, False, reason="juda katta fayl")
            size = image_size(r.content)
            if size and min(size) < MIN_SIDE:
                return Fetched(url, False, size=size, reason=f"juda kichik ({size[0]}x{size[1]})")
            if not size and len(r.content) < UNKNOWN_SIZE_MIN_BYTES:
                return Fetched(url, False, reason="juda kichik (eskiz)")
            return Fetched(url, True, r.content, ext, size)
    return Fetched(url, False, reason=reason)


def fetch_best(url: str, *, referer: str = "") -> Fetched:
    """Avval kattaroq variantlar, keyin asl havola — eng katta ishlagani."""
    best = None
    for candidate in [*bigger_variants(url), url]:
        f = fetch(candidate, referer=referer)
        if f.ok and (best is None or f.area > best.area):
            best = f
            if f.size and min(f.size) >= 1000:
                break  # yetarlicha katta
        if candidate == url and best is None:
            return f
    return best


_IMG_URL = re.compile(r"https?://[^\s)\"'<>\]]+?\.(?:jpe?g|png|webp|avif)(?:\?[^\s)\"'<>\]]*)?", re.I)
_SKIP = ("logo", "icon", "sprite", "favicon", "avatar", "banner", "placeholder", "pixel", "badge", "flag")
# Bot himoyasi / xato sahifalari rasmlari (Ozon "incidents/warn.png", captcha va h.k.) — tovar rasmi emas.
_JUNK = (
    "/incidents/",
    "captcha",
    "/warn.",
    "warning.",
    "/error",
    "no-image",
    "noimage",
    "no_photo",
    "nophoto",
    "stub.",
    "/blank.",
    "challenge",
)


def is_junk(url: str) -> bool:
    low = url.lower()
    return any(s in low for s in _SKIP + _JUNK)


def urls_in_text(text: str, limit: int = 20) -> list[str]:
    """Sahifa matnidagi (markdown/HTML) rasm havolalari — logotip, belgi va h.k. tashlanadi."""
    out = []
    for u in _IMG_URL.findall(text or ""):
        if not is_junk(u) and u not in out:
            out.append(u)
        if len(out) >= limit:
            break
    return out
