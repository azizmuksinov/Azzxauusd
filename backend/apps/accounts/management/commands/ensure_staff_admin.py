"""Birinchi administrator: login va parol muhit o'zgaruvchilaridan (ADMIN_LOGIN, ADMIN_PASSWORD).

Server ishga tushganda chaqiriladi. O'zgaruvchilar berilgan bo'lsa — shu login/parolli administrator
yaratiladi (bor bo'lsa paroli yangilanadi) va namuna (demo) parolli akkauntlar yopiladi. Berilmagan bo'lsa —
hech narsa o'zgarmaydi (demo'da namuna login/parol ishlaydi).
"""

import os

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import staff_auth
from apps.accounts.models import Role, User
from apps.core.exceptions import ApiError
from apps.core.phone import normalize_phone

DEMO_ADMIN_PHONE = "+998900000002"


class Command(BaseCommand):
    help = "ADMIN_LOGIN / ADMIN_PASSWORD bo'yicha administratorni yaratadi yoki parolini yangilaydi."

    def handle(self, *args, **options):
        login = os.environ.get("ADMIN_LOGIN", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not login and not password:
            self.stdout.write("ADMIN_LOGIN/ADMIN_PASSWORD berilmagan — o'zgarish yo'q.")
            return
        if not login or not password:
            raise CommandError("ADMIN_LOGIN va ADMIN_PASSWORD birga beriladi.")
        try:
            login = staff_auth.clean_login(login)
            phone = normalize_phone(os.environ.get("ADMIN_PHONE") or DEMO_ADMIN_PHONE)
            user = (
                User.objects.filter(login=login).first()
                or User.objects.filter(phone=phone).first()
                or User.objects.create_user(phone, first_name="Administrator")
            )
            user.is_active = True
            staff_auth.set_credentials(user, login=login, password=password)
        except ApiError as exc:
            raise CommandError(str(exc.detail)) from exc
        user.groups.add(Group.objects.get_or_create(name=Role.ADMIN)[0])
        # Namuna parol bilan qolgan akkauntlar yopiladi (yangi parolni administrator beradi).
        closed = 0
        for other in User.objects.exclude(pk=user.pk).exclude(login__isnull=True):
            if other.has_usable_password() and other.check_password(settings.DEMO_STAFF_PASSWORD):
                other.set_unusable_password()
                other.save(update_fields=["password"])
                staff_auth.revoke_sessions(other)
                closed += 1
        self.stdout.write(f"Administrator tayyor: {login}. Namuna parolli akkauntlar yopildi: {closed}.")
