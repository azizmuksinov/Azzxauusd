from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import DEMO_MODE, SECRET_KEY, SMS_BACKEND, env

DEBUG = False
if SECRET_KEY.startswith("dev-insecure"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY o'rnatilmagan")
if DEMO_MODE:
    raise ImproperlyConfigured("Production'da DEMO_MODE yoqib bo'lmaydi")
if SMS_BACKEND == "console":
    raise ImproperlyConfigured("Production'da SMS_BACKEND=console mumkin emas (kodlar logga yoziladi)")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
