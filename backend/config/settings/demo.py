"""Hugging Face Spaces demo muhiti: faqat soxta ma'lumotlar, SMS-kod javobda qaytariladi."""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = False
DEMO_MODE = True
ALLOWED_HOSTS = ["*"]
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'demo.sqlite3'}")}
# Bir nechta gunicorn worker o'rtasida OTP umumiy bo'lishi uchun DB-kesh.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "cache_table"}}
CELERY_TASK_ALWAYS_EAGER = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
