#!/bin/bash
set -e
# Secret berilmagan bo'lsa — har ishga tushishda tasodifiy kalit (demo uchun yetarli).
if [ -z "$DJANGO_SECRET_KEY" ]; then
  DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))")
  export DJANGO_SECRET_KEY
fi
python manage.py migrate --noinput -v0
python manage.py createcachetable -v0
python manage.py seed_demo
if [ -n "$DEMO_ADMIN_PHONE" ] && [ -n "$DEMO_ADMIN_PASSWORD" ]; then
  python manage.py shell -c "
from apps.accounts.models import User
from apps.core.phone import normalize_phone
import os
p = normalize_phone(os.environ['DEMO_ADMIN_PHONE'])
u = User.objects.filter(phone=p).first() or User.objects.create_superuser(p, os.environ['DEMO_ADMIN_PASSWORD'])
u.set_password(os.environ['DEMO_ADMIN_PASSWORD']); u.is_staff = u.is_superuser = True; u.save()
"
fi

gunicorn config.wsgi -b 127.0.0.1:8000 -w 2 --timeout 180 --access-logfile - --forwarded-allow-ips="*" &
(cd /home/user/web && HOSTNAME=127.0.0.1 PORT=3000 node server.js) &
nginx -c /home/user/app/nginx.conf -g "daemon off;" &

# Biror jarayon to'xtasa — konteyner chiqadi va HF uni qayta ishga tushiradi.
wait -n
exit 1
