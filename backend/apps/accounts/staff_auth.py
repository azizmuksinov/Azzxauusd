"""Xodimlar login va parol bilan kiradi (xaridorlar — SMS-kod bilan).

Login va parolni faqat administrator beradi (Xodimlar bo'limi) — xodim o'zi ro'yxatdan o'tmaydi va parolini
o'zi tiklay olmaydi. Birinchi administrator muhit o'zgaruvchilaridan yaratiladi (`ensure_staff_admin`).
Cheklovlar: bitta login bo'yicha ketma-ket xato urinishlar va bitta IP bo'yicha soatlik limit.
"""

import re

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError

from apps.core.exceptions import ApiError

from .models import User
from .otp import RateLimited, _incr_window

LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
MAX_FAILS = 5  # shuncha xato urinishdan keyin login vaqtincha yopiladi
LOCK_SECONDS = 15 * 60
MAX_PER_IP_PER_HOUR = 40


class BadCredentials(ApiError):
    status_code = 401
    default_code = "bad_credentials"
    default_detail = "Login yoki parol noto'g'ri."


def is_staff_account(user: User) -> bool:
    """Xodim (biror roli bor yoki superuser) — SMS-kod bilan kira olmaydi."""
    return user.is_superuser or user.groups.exists()


def clean_login(value: str) -> str:
    login = (value or "").strip().lower()
    if not LOGIN_RE.match(login):
        raise ApiError(
            "login_invalid",
            "Login 3–32 belgi: lotin harflari, raqamlar, nuqta, chiziqcha yoki pastki chiziq.",
        )
    return login


def check_password_rules(password: str, user: User | None = None) -> None:
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ApiError("password_weak", " ".join(exc.messages)) from exc


def set_credentials(user: User, *, login: str | None = None, password: str | None = None) -> None:
    """Login va/yoki parolni o'rnatadi. Parol o'zgarsa — xodimning ochiq seanslari yopiladi."""
    if login is not None:
        login = clean_login(login)
        if User.objects.filter(login=login).exclude(pk=user.pk).exists():
            raise ApiError("login_taken", "Bu login band. Boshqasini tanlang.", status_code=409)
        user.login = login
    if password is not None:
        check_password_rules(password, user)
        user.set_password(password)
    user.save()
    if password is not None:
        revoke_sessions(user)
        cache.delete(f"stafflogin:fails:{user.login}")


def revoke_sessions(user: User) -> None:
    """Xodimning barcha refresh tokenlari bekor qilinadi (15 daqiqa ichida access token ham tugaydi)."""
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


def authenticate(login: str, password: str, ip: str | None) -> User:
    login = (login or "").strip().lower()
    if ip and _incr_window(f"stafflogin:ip:{ip}", 3600) > MAX_PER_IP_PER_HOUR:
        raise RateLimited()
    fails_key = f"stafflogin:fails:{login}"
    if (cache.get(fails_key) or 0) >= MAX_FAILS:
        raise RateLimited(
            message="Juda ko'p xato urinish. 15 daqiqadan keyin qayta urinib ko'ring.",
            extra={"retry_after": LOCK_SECONDS},
        )
    user = User.objects.filter(login=login).first() if login else None
    if user is None or not user.has_usable_password():
        make_password(password)  # login bor-yo'qligi javob vaqtidan bilinmasin
        ok = False
    else:
        ok = user.check_password(password)
    if not ok or not user.is_active or not is_staff_account(user):
        left = MAX_FAILS - _incr_window(fails_key, LOCK_SECONDS)
        raise BadCredentials(extra={"attempts_left": max(left, 0)})
    cache.delete(fails_key)
    return user


def demo_accounts() -> list[dict]:
    """Demo rejimda (administrator paroli berilmagan bo'lsa) kirish sahifasida ko'rsatiladigan namunalar."""
    import os

    if not settings.DEMO_MODE or os.environ.get("ADMIN_PASSWORD"):
        return []
    out = []
    for login, label in (("admin", "Administrator (barcha bo'limlar)"), ("kuryer", "Kuryer")):
        user = User.objects.filter(login=login, is_active=True).first()
        if user and user.check_password(settings.DEMO_STAFF_PASSWORD):
            out.append({"label": label, "login": login, "password": settings.DEMO_STAFF_PASSWORD})
    return out
