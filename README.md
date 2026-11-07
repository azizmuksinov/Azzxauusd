# Onlayn do'kon

Bitta sotuvchili (single-vendor) maishiy texnika va elektronika onlayn do'koni (O'zbekiston).
Yetkazish faqat eshikkacha: o'z kuryerlarimiz, Fargo, BTS Express.

| Papka | Mazmuni |
|---|---|
| [`docs/`](docs/) | Arxitektura, MB sxemasi (ER), API ro'yxati, ochiq savollar |
| [`backend/`](backend/) | Django + DRF monolit (API, admin, Celery) |
| [`infra/hf-space/`](infra/hf-space/) | Demo muhitga joylash (Docker) |

## Modullar holati

| Modul | Holat | README |
|---|---|---|
| core (xato formati, telefon, i18n, transliteratsiya) | ✅ | [backend/apps/core](backend/apps/core/README.md) |
| geo (viloyat/tuman) | ✅ | [backend/apps/geo](backend/apps/geo/README.md) |
| notifications (SMS: console, Eskiz) | ✅ | [backend/apps/notifications](backend/apps/notifications/README.md) |
| accounts / auth (SMS-kod, JWT, profil, manzillar, rollar) | ✅ | [backend/apps/accounts](backend/apps/accounts/README.md) |
| catalog / inventory | ⏳ keyingi | |
| cart / checkout, payments, orders, logistics, admin, sync_1c | ⏳ | |

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
