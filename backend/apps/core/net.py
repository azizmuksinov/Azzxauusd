"""Tashqi havolalarni xavfsiz yuklash: faqat ochiq internet manzillari (SSRF himoyasi).

AI javobidagi yoki xodim kiritgan havola serverni ichki tarmoqqa (localhost, 10.x, 192.168.x, bulut
metadata 169.254.169.254 va h.k.) so'rov yuborishga majbur qilmasligi kerak.
"""

import ipaddress
import socket
from urllib.parse import urlparse


def is_public_url(url: str) -> bool:
    """http(s) va host ochiq (global) IP'ga yechilsa — True. Yechilmasa — True (so'rov o'zi xato beradi)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        except OSError:
            return True
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    return all(a.is_global for a in addresses)


def safe_get(client, url: str, *, headers: dict | None = None, max_redirects: int = 4):
    """GET, yo'naltirishlar qo'lda kuzatiladi: har bir manzil ochiq ekani tekshiriladi.

    Ochiq sayt ichki manzilga yo'naltirsa (redirect) — httpx.HTTPError. `client` — follow_redirects=False.
    """
    import httpx

    for _ in range(max_redirects + 1):
        if not is_public_url(url):
            raise httpx.RequestError(f"ichki tarmoq manzili: {url}")
        r = client.get(url, headers=headers, follow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = str(r.url.join(r.headers["location"]))
            continue
        return r
    raise httpx.TooManyRedirects("juda ko'p yo'naltirish")
