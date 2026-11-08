"""Hugging Face Spaces demo muhiti: faqat soxta ma'lumotlar, SMS-kod javobda qaytariladi."""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, MIDDLEWARE, env

DEBUG = False
DEMO_MODE = True
ALLOWED_HOSTS = ["*"]
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'demo.sqlite3'}")}
# Bir nechta gunicorn worker o'rtasida OTP umumiy bo'lishi uchun DB-kesh.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "cache_table"}}
CELERY_TASK_ALWAYS_EAGER = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HF Space ilovani huggingface.co ichida iframe'da ko'rsatadi:
# X-Frame-Options: DENY o'rniga CSP frame-ancestors bilan faqat huggingface.co'ga ruxsat.
MIDDLEWARE = [m for m in MIDDLEWARE if m != "django.middleware.clickjacking.XFrameOptionsMiddleware"]
MIDDLEWARE.insert(1, "apps.core.middleware.FrameAncestorsMiddleware")
FRAME_ANCESTORS = ["https://huggingface.co"]
# Iframe ichida admin login ishlashi uchun cookie'lar uchinchi tomon kontekstida ham yuborilsin.
# Lokal HTTP sinovi uchun COOKIE_SECURE=false (HF Space'da HTTPS — true).
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = env.bool("COOKIE_SECURE", default=True)
# SameSite=None faqat Secure bilan ishlaydi (brauzer talabi).
SESSION_COOKIE_SAMESITE = CSRF_COOKIE_SAMESITE = "None" if SESSION_COOKIE_SECURE else "Lax"
CSRF_TRUSTED_ORIGINS = [
    "https://*.hf.space",
    "https://huggingface.co",
    *env.list("EXTRA_CSRF_ORIGINS", default=[]),
]
# nginx orqasida: havolalar (pagination "next") ommaviy domen bilan yasalsin.
USE_X_FORWARDED_HOST = True

SERVE_MEDIA = True
