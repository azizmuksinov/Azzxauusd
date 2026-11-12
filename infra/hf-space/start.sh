#!/bin/bash
set -e
# Secret berilmagan bo'lsa — har ishga tushishda tasodifiy kalit (demo uchun yetarli).
if [ -z "$DJANGO_SECRET_KEY" ]; then
  DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))")
  export DJANGO_SECRET_KEY
fi
# Doimiy saqlash (HF_TOKEN secret bo'lsa): avvalgi baza va rasmlarni Dataset'dan tiklash.
DEMO_RESTORED=0
python /home/user/app/persist.py restore && DEMO_RESTORED=1
export DEMO_RESTORED
python manage.py migrate --noinput -v0
python manage.py createcachetable -v0
# Tiklangan bazada demo ma'lumotlar qayta yozilmaydi (xodim tahrirlari saqlanib qolsin).
[ "$DEMO_RESTORED" = "1" ] || python manage.py seed_demo
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
P_API=$!
(cd /home/user/web && HOSTNAME=127.0.0.1 PORT=3000 node server.js) &
P_WEB=$!
nginx -c /home/user/app/nginx.conf -g "daemon off;" &
P_NGINX=$!

# AI kaliti/modeli tekshiruvi — faqat log uchun; tugashi konteynerni to'xtatmaydi (wait -n faqat 3 ta serverni kutadi).
# Faqat bepul tekshiruv (modellar ro'yxati); generatsiya va rasm qidirish kvota sarflamasligi uchun — ixtiyoriy.
# Namuna tovarlar rasmsiz qolmasin: fonda bepul qidiruv bilan rasm topiladi (DEMO_AI_IMAGES=0 — o'chirish;
# =1 — bepul yo'l topmasa, internetdan qidira oladigan AI ham ishlatiladi).
(python manage.py ai_check || true
 case "${DEMO_AI_IMAGES:-free}" in
   0) ;;
   1) python manage.py ai_fill_images --limit 20 || true ;;
   *) [ "$DEMO_RESTORED" = "1" ] || python manage.py ai_fill_images --limit 20 --free-only || true ;;
 esac) &

# Har 5 daqiqada o'zgarishlarni Dataset'ga saqlash; to'xtatilganda — oxirgi saqlash.
python /home/user/app/persist.py sync &
P_SYNC=$!
shutdown() {
  kill -TERM "$P_SYNC" 2>/dev/null || true
  wait "$P_SYNC" 2>/dev/null || true
  kill "$P_API" "$P_WEB" "$P_NGINX" 2>/dev/null || true
  exit "${1:-0}"
}
trap 'shutdown 0' TERM INT

# Asosiy serverlardan biri to'xtasa — saqlab, konteyner chiqadi va HF uni qayta ishga tushiradi.
wait -n "$P_API" "$P_WEB" "$P_NGINX"
shutdown 1
