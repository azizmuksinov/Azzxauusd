#!/bin/sh
set -e
# Secret berilmagan bo'lsa — har ishga tushishda tasodifiy kalit (demo uchun yetarli).
if [ -z "$DJANGO_SECRET_KEY" ]; then
  DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))")
  export DJANGO_SECRET_KEY
fi
python manage.py migrate --noinput -v0
python manage.py createcachetable -v0
if [ -n "$DEMO_ADMIN_PHONE" ] && [ -n "$DEMO_ADMIN_PASSWORD" ]; then
  python manage.py shell -c "
from apps.accounts.models import User
from apps.core.phone import normalize_phone
import os
p = normalize_phone(os.environ['DEMO_ADMIN_PHONE'])
if not User.objects.filter(phone=p).exists():
    User.objects.create_superuser(p, os.environ['DEMO_ADMIN_PASSWORD'])
"
fi
exec gunicorn config.wsgi -b 0.0.0.0:7860 -w 2 --access-logfile - --forwarded-allow-ips="*"
