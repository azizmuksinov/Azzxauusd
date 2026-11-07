"""Umumiy sozlamalar. Muhitga xos qiymatlar env o'zgaruvchilardan olinadi."""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Demo rejim: SMS-kod API javobida qaytariladi. Production'da HECH QACHON yoqilmaydi.
DEMO_MODE = env.bool("DEMO_MODE", default=False)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 3rd party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    # loyiha modullari
    "apps.core",
    "apps.geo",
    "apps.notifications",
    "apps.accounts",
    "apps.catalog",
    "apps.inventory",
    "apps.cart",
    "apps.logistics",
    "apps.orders",
    "apps.payments",
    "apps.backoffice",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {"default": env.db("DATABASE_URL", default="postgres://postgres:postgres@localhost:5432/dokon")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = {"default": env.cache("CACHE_URL", default="redis://localhost:6379/1")}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "uz"
LANGUAGES = [("uz", "O'zbekcha"), ("uz-cyrl", "Ўзбекча"), ("ru", "Русский")]
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Onlayn do'kon API",
    "DESCRIPTION": "Bitta sotuvchili maishiy texnika va elektronika do'koni API'si.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "OrderStatusEnum": "apps.orders.models.OrderStatus",
        "ProductStatusEnum": "apps.catalog.models.Product.Status",
        "ImportStatusEnum": "apps.catalog.models.ProductImport.Status",
        "SerialUnitStatusEnum": "apps.inventory.models.SerialUnit.Status",
        "DocumentStatusEnum": "apps.backoffice.models.DocStatus",
        "PaymentRecordStatusEnum": "apps.payments.models.Payment.Status",
    },
}

# --- OTP ---
OTP = {
    "LENGTH": 6,
    "TTL_SECONDS": 120,
    "MAX_ATTEMPTS": 5,
    "RESEND_COOLDOWN_SECONDS": 60,
    "MAX_PER_PHONE_PER_HOUR": 5,
    "MAX_PER_IP_PER_HOUR": 20,
}

# --- SMS ---
# "console" — demo/dev: SMS yuborilmaydi, logga yoziladi.
# "eskiz"   — Eskiz.uz (notify.eskiz.uz).
SMS_BACKEND = env("SMS_BACKEND", default="console")
SMS_ASYNC = env.bool("SMS_ASYNC", default=True)
ESKIZ = {
    "BASE_URL": env("ESKIZ_BASE_URL", default="https://notify.eskiz.uz/api"),
    "EMAIL": env("ESKIZ_EMAIL", default=""),
    "PASSWORD": env("ESKIZ_PASSWORD", default=""),
    "FROM": env("ESKIZ_FROM", default="4546"),
    "TIMEOUT": env.float("ESKIZ_TIMEOUT", default=10.0),
}
OTP_SMS_TEMPLATE = env(
    "OTP_SMS_TEMPLATE",
    default="Tasdiqlash kodi: {code}. Kodni hech kimga bermang.",
)

# --- Celery ---
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# --- Qidiruv ---
# "db" — PostgreSQL/SQLite (demo, test); "meilisearch" — production.
SEARCH_BACKEND = env("SEARCH_BACKEND", default="db")
MEILISEARCH = {
    "URL": env("MEILISEARCH_URL", default="http://localhost:7700"),
    "API_KEY": env("MEILISEARCH_API_KEY", default=""),
    "INDEX": env("MEILISEARCH_INDEX", default="products"),
    "TIMEOUT": env.float("MEILISEARCH_TIMEOUT", default=3.0),
}

# --- Katalog ---
CATALOG_COMPARE_MAX = 6

CELERY_BEAT_SCHEDULE = {
    "cancel-unpaid-orders": {"task": "apps.orders.tasks.cancel_unpaid_orders_task", "schedule": 60.0},
    "release-expired-reservations": {
        "task": "apps.inventory.tasks.release_expired_reservations",
        "schedule": 60.0,
    },
    "cleanup-guest-carts": {"task": "apps.cart.tasks.cleanup_guest_carts_task", "schedule": 24 * 3600.0},
}

# --- Logistika ---
# Yoqilgan yetkazish provayderlari. Hozircha faqat "own" (admin kiritgan tariflar); Fargo/BTS keyin.
LOGISTICS_PROVIDERS = env.list("LOGISTICS_PROVIDERS", default=["own"])

# --- To'lovlar ---
# Yoqilgan onlayn to'lov tizimlari (kalitlar kiritilgach). Kalitlar faqat env/secret'da.
PAYMENT_PROVIDERS = env.list("PAYMENT_PROVIDERS", default=["payme", "click", "uzum"])
PAYME = {
    "MERCHANT_ID": env("PAYME_MERCHANT_ID", default=""),
    "KEY": env("PAYME_KEY", default=""),  # kassa kaliti (test yoki prod)
    "CHECKOUT_URL": env(
        "PAYME_CHECKOUT_URL", default="https://checkout.paycom.uz"
    ),  # test: checkout.test.paycom.uz
    "ACCOUNT_FIELD": env("PAYME_ACCOUNT_FIELD", default="order_id"),
    # Fiskal chek (OFD) uchun — S-15: haqiqiy kodlar buxgalter/OFD bilan kelishiladi
    "DEFAULT_PACKAGE_CODE": env("PAYME_DEFAULT_PACKAGE_CODE", default=""),
    "DELIVERY_MXIK": env("PAYME_DELIVERY_MXIK", default=""),
    "DELIVERY_PACKAGE_CODE": env("PAYME_DELIVERY_PACKAGE_CODE", default=""),
    "DELIVERY_VAT": env.int("PAYME_DELIVERY_VAT", default=12),
}
CLICK = {
    "SERVICE_ID": env("CLICK_SERVICE_ID", default=""),
    "MERCHANT_ID": env("CLICK_MERCHANT_ID", default=""),
    "SECRET_KEY": env("CLICK_SECRET_KEY", default=""),
    "CHECKOUT_URL": env("CLICK_CHECKOUT_URL", default="https://my.click.uz/services/pay"),
}
UZUM = {
    "SERVICE_ID": env("UZUM_SERVICE_ID", default=""),
    "LOGIN": env("UZUM_LOGIN", default=""),
    "PASSWORD": env("UZUM_PASSWORD", default=""),
    # Uzum hujjatidagi to'lov havolasi shabloni: {service_id} {order} {amount} {return_url}
    "PAYMENT_URL_TEMPLATE": env("UZUM_PAYMENT_URL_TEMPLATE", default=""),
}
# Provayderlarning rasmiy IP manzillari (hujjatdan).
# Bo'sh — IP tekshirilmaydi (imzo/parol tekshiruvi baribir majburiy).
PAYMENT_ALLOWED_IPS = {
    "payme": env.list("PAYME_ALLOWED_IPS", default=[]),
    "click": env.list("CLICK_ALLOWED_IPS", default=[]),
    "uzum": env.list("UZUM_ALLOWED_IPS", default=[]),
}
