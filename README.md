# Onlayn do'kon

Bitta sotuvchili (single-vendor) maishiy texnika va elektronika onlayn do'koni (O'zbekiston).
Yetkazish faqat eshikkacha: o'z kuryerlarimiz, Fargo, BTS Express.

| Papka | Mazmuni |
|---|---|
| [`docs/`](docs/) | Arxitektura, MB sxemasi (ER), API ro'yxati, ochiq savollar |
| [`backend/`](backend/) | Django + DRF monolit (API, admin, Celery) |
| [`web/`](web/) | Xaridor veb-do'koni (Next.js 15, Tailwind) |
| [`infra/hf-space/`](infra/hf-space/) | Demo: bitta konteynerda nginx + Django + Next.js |

## Modullar holati

| Modul | Holat | README |
|---|---|---|
| core (xato formati, telefon, i18n, transliteratsiya, biznes sozlamalari) | ✅ | [backend/apps/core](backend/apps/core/README.md) |
| geo (viloyat/tuman) | ✅ | [backend/apps/geo](backend/apps/geo/README.md) |
| notifications (SMS: console, Eskiz) | ✅ | [backend/apps/notifications](backend/apps/notifications/README.md) |
| accounts / auth (SMS-kod, JWT, profil, manzillar, rollar) | ✅ | [backend/apps/accounts](backend/apps/accounts/README.md) |
| catalog (katalog, filtrlar, fasetlar, qidiruv, solishtirish, sevimlilar, Excel import) | ✅ | [backend/apps/catalog](backend/apps/catalog/README.md) |
| inventory (ombor, qoldiq, rezerv, seriya/IMEI) | ✅ | [backend/apps/inventory](backend/apps/inventory/README.md) |
| cart (savat, mehmon savati, birlashtirish) | ✅ | [backend/apps/cart](backend/apps/cart/README.md) |
| logistics (zonalar, tariflar, qavatga ko'tarish; Fargo/BTS — keyin) | ✅ MVP | [backend/apps/logistics](backend/apps/logistics/README.md) |
| orders (checkout, buyurtma, statuslar, bekor qilish) | ✅ | [backend/apps/orders](backend/apps/orders/README.md) |
| payments (Payme, Click, Uzum Bank; webhook imzolari, avans) | ✅ (kalitlar kutilmoqda) | [backend/apps/payments](backend/apps/payments/README.md) |
| backoffice (1C o'rniga): ta'minotchilar, kirim (o'rtacha tannarx), ko'chirish, hisobdan chiqarish, kassa | ✅ | [backend/apps/backoffice](backend/apps/backoffice/README.md) |
| veb-do'kon (katalog, filtrlar, savat, SMS-login, checkout, buyurtmalar; uz/ўз/ru) | ✅ | [web](web/README.md) |
| kuryer ilovasi API, admin (yig'ish, hisobotlar), warranty, reviews, OFD, mobil ilova (Flutter) | ⏳ | |

## Tez ishga tushirish

```bash
cp .env.example backend/.env
docker compose up --build
# http://localhost:8000/api/docs/  — Swagger
```

Docker'siz:

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgres://postgres:postgres@localhost:5432/dokon
python manage.py migrate
python manage.py createsuperuser        # telefon + parol (faqat xodimlar uchun)
python manage.py runserver
```

## Testlar

```bash
cd backend
pytest --cov=apps          # PostgreSQL kerak (DATABASE_URL)
ruff check . && ruff format --check .
python manage.py spectacular --validate --file openapi.yml
```

CI (GitHub Actions): lint → migratsiyalar tekshiruvi → testlar → OpenAPI → Docker build → demo deploy.
