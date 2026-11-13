"""SMS orqali bir martalik kod (OTP).

Kod bazaga yozilmaydi: keshda (prod — Redis) faqat HMAC xeshi saqlanadi.
Cheklovlar: qayta yuborish oralig'i, telefon va IP bo'yicha soatlik limit, urinishlar soni.
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from apps.core.exceptions import ApiError
from apps.notifications.services import send_sms


def _cfg(key: str) -> int:
    return settings.OTP[key]


def _hash(phone: str, code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _incr_window(key: str, ttl: int) -> int:
    """Belgilangan oyna ichidagi hisoblagich (cache.add + incr — atomar)."""
    cache.add(key, 0, ttl)
    try:
        return cache.incr(key)
    except ValueError:  # kalit shu orada muddati o'tib ketgan
        cache.set(key, 1, ttl)
        return 1


@dataclass
class OtpRequestResult:
    expires_in: int
    resend_in: int
    debug_code: str | None = None


class RateLimited(ApiError):
    status_code = 429
    default_code = "rate_limited"
    default_detail = "Juda ko'p urinish. Birozdan keyin qayta urinib ko'ring."


def request_otp(phone: str, ip: str | None) -> OtpRequestResult:
    cooldown = _cfg("RESEND_COOLDOWN_SECONDS")
    ttl = _cfg("TTL_SECONDS")

    if not cache.add(f"otp:cooldown:{phone}", 1, cooldown):
        raise RateLimited(extra={"retry_after": cooldown})
    if _incr_window(f"otp:hour:phone:{phone}", 3600) > _cfg("MAX_PER_PHONE_PER_HOUR"):
        raise RateLimited()
    if ip and _incr_window(f"otp:hour:ip:{ip}", 3600) > _cfg("MAX_PER_IP_PER_HOUR"):
        raise RateLimited()

    length = _cfg("LENGTH")
    code = f"{secrets.randbelow(10**length):0{length}d}"
    cache.set(f"otp:code:{phone}", {"hash": _hash(phone, code), "exp": time.time() + ttl}, ttl)
    cache.delete(f"otp:attempts:{phone}")

    send_sms(
        phone,
        settings.OTP_SMS_TEMPLATE.format(code=code),
        template_code="otp",
        log_body=settings.OTP_SMS_TEMPLATE.format(code="******"),
    )
    return OtpRequestResult(
        expires_in=ttl,
        resend_in=cooldown,
        debug_code=code if settings.DEMO_MODE else None,
    )


class OtpInvalid(ApiError):
    default_code = "otp_invalid"
    default_detail = "Kod noto'g'ri."


class OtpExpired(ApiError):
    default_code = "otp_expired"
    default_detail = "Kod muddati tugagan yoki so'ralmagan. Yangi kod so'rang."


def verify_otp(phone: str, code: str) -> None:
    key = f"otp:code:{phone}"
    attempts_key = f"otp:attempts:{phone}"
    data = cache.get(key)
    remaining_ttl = int(data["exp"] - time.time()) if data else 0
    if remaining_ttl <= 0:
        raise OtpExpired()

    # Atomar hisoblagich: parallel so'rovlar bilan limitni chetlab o'tib bo'lmaydi.
    max_attempts = _cfg("MAX_ATTEMPTS")
    attempt = _incr_window(attempts_key, remaining_ttl)
    if attempt > max_attempts:
        cache.delete_many([key, attempts_key])
        raise OtpExpired(message="Urinishlar soni tugadi. Yangi kod so'rang.")

    if not hmac.compare_digest(data["hash"], _hash(phone, code)):
        attempts_left = max_attempts - attempt
        if attempts_left <= 0:
            cache.delete_many([key, attempts_key])
        raise OtpInvalid(extra={"attempts_left": attempts_left})

    cache.delete_many([key, attempts_key])
