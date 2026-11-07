# Hugging Face Spaces (Docker SDK) — DEMO muhit. Faqat soxta ma'lumotlar!
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.demo \
    DATABASE_URL=sqlite:////home/user/data/demo.sqlite3 \
    SMS_BACKEND=console

# HF Spaces konteynerni uid 1000 bilan ishga tushiradi.
RUN useradd --uid 1000 --create-home user
WORKDIR /home/user/app

COPY --chown=user backend/requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=user backend/ .
COPY --chown=user start.sh .
RUN python manage.py collectstatic --noinput -v0 && chmod +x start.sh

USER user
RUN mkdir -p /home/user/data
EXPOSE 7860
CMD ["./start.sh"]
