# Hugging Face Spaces (Docker SDK) — DEMO: veb-do'kon (Next.js) + API/admin (Django) bitta konteynerda.
# Faqat soxta ma'lumotlar! Tashqi port 7860: nginx -> /api,/admin,/static Django'ga, qolgani Next'ga.

# --- 1. Veb-do'konni yig'ish ---
FROM node:22-slim AS web
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_DEMO=1
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN mkdir -p public && npm run build \
    && cp -r .next/static .next/standalone/.next/static && cp -r public .next/standalone/public

# --- 2. Ishlash muhiti ---
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.demo \
    DATABASE_URL=sqlite:////home/user/data/demo.sqlite3 \
    MEDIA_ROOT=/home/user/data/media \
    SMS_BACKEND=console \
    NEXT_TELEMETRY_DISABLED=1
RUN apt-get update && apt-get install -y --no-install-recommends nginx libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node

# HF Spaces konteynerni uid 1000 bilan ishga tushiradi.
RUN useradd --uid 1000 --create-home user
WORKDIR /home/user/app

COPY --chown=user backend/requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=user backend/ .
COPY --chown=user --from=web /web/.next/standalone /home/user/web
COPY --chown=user nginx.conf start.sh ./
RUN python manage.py collectstatic --noinput -v0 && chmod +x start.sh

USER user
# Yoziladigan papkalar — faqat user egasi bo'lgan joyda (/home/user/app root egasida).
RUN mkdir -p /home/user/data/media
EXPOSE 7860
CMD ["./start.sh"]
