"""Eskiz.uz SMS provayderi (https://notify.eskiz.uz).

Oqim: POST /auth/login (email, password) -> token (Redis/keshda saqlanadi)
      POST /message/sms/send (mobile_phone=998XXXXXXXXX, message, from)
Token muddati o'tsa (401) — bir marta qayta login qilinadi.

Eslatma: Eskiz'ning bepul test rejimida faqat Eskiz bergan test matnini yuborish mumkin;
OTP kodi bor SMS uchun balans to'ldirilgan va shablon tasdiqlangan bo'lishi kerak.
"""

import logging

import httpx
from django.conf import settings
from django.core.cache import cache

from apps.core.phone import mask_phone

from .base import SmsBackend, SmsError, SmsResult

logger = logging.getLogger("sms.eskiz")

TOKEN_CACHE_KEY = "sms:eskiz:token"  # noqa: S105 - kesh kaliti nomi
TOKEN_TTL = 25 * 24 * 3600  # Eskiz tokeni ~30 kun amal qiladi


class EskizSmsBackend(SmsBackend):
    name = "eskiz"

    def __init__(self, client: httpx.Client | None = None):
        cfg = settings.ESKIZ
        self.base_url = cfg["BASE_URL"].rstrip("/")
        self.email = cfg["EMAIL"]
        self.password = cfg["PASSWORD"]
        self.sender = cfg["FROM"]
        self.client = client or httpx.Client(timeout=cfg["TIMEOUT"])

    # --- token ---
    def _login(self) -> str:
        if not self.email or not self.password:
            raise SmsError("ESKIZ_EMAIL / ESKIZ_PASSWORD o'rnatilmagan", retryable=False)
        try:
            resp = self.client.post(
                f"{self.base_url}/auth/login", data={"email": self.email, "password": self.password}
            )
        except httpx.HTTPError as exc:
            raise SmsError(f"Eskiz login: tarmoq xatosi: {exc}") from exc
        if resp.status_code != 200:
            raise SmsError(f"Eskiz login xatosi: HTTP {resp.status_code}", retryable=resp.status_code >= 500)
        token = (resp.json().get("data") or {}).get("token")
        if not token:
            raise SmsError("Eskiz login javobida token yo'q", retryable=False)
        cache.set(TOKEN_CACHE_KEY, token, TOKEN_TTL)
        return token

    def _token(self, force: bool = False) -> str:
        token = None if force else cache.get(TOKEN_CACHE_KEY)
        return token or self._login()

    # --- send ---
    def _post_send(self, token: str, phone: str, text: str) -> httpx.Response:
        return self.client.post(
            f"{self.base_url}/message/sms/send",
            headers={"Authorization": f"Bearer {token}"},
            data={"mobile_phone": phone.lstrip("+"), "message": text, "from": self.sender},
        )

    def send(self, phone: str, text: str) -> SmsResult:
        try:
            resp = self._post_send(self._token(), phone, text)
            if resp.status_code == 401:
                resp = self._post_send(self._token(force=True), phone, text)
        except httpx.HTTPError as exc:
            raise SmsError(f"Eskiz: tarmoq xatosi: {exc}") from exc

        if resp.status_code >= 400:
            logger.warning("Eskiz xatosi %s -> %s: %s", mask_phone(phone), resp.status_code, resp.text[:300])
            raise SmsError(f"Eskiz: HTTP {resp.status_code}", retryable=resp.status_code >= 500)

        data = resp.json()
        return SmsResult(provider=self.name, message_id=str(data.get("id", "")))
