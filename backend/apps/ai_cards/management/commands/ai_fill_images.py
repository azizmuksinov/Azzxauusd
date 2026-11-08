"""Rasmsiz faol tovarlarga AI orqali internetdan rasm topish (demo katalog uchun)."""

from django.core.management.base import BaseCommand

from apps.ai_cards import client, services
from apps.catalog.models import Product
from apps.core.exceptions import ApiError


class Command(BaseCommand):
    help = "Rasmsiz faol tovarlarga AI (Google qidiruvi) orqali rasm topib yuklaydi."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20, help="Ko'pi bilan nechta tovar")

    def handle(self, *args, limit, **opts):
        products = list(
            Product.objects.filter(status=Product.Status.ACTIVE, images__isnull=True)
            .select_related("brand")
            .order_by("id")[:limit]
        )
        self.stdout.write(f"AI rasmlar: {len(products)} ta rasmsiz tovar.")
        done = 0
        for p in products:
            try:
                n = services.find_images(p)
            except (client.AiError, ApiError) as exc:
                self.stdout.write(f"AI rasmlar: to'xtatildi — {getattr(exc, 'message', None) or exc}")
                break
            done += bool(n)
            self.stdout.write(f"AI rasmlar: {p.slug}: {n} ta")
        self.stdout.write(f"AI rasmlar: tugadi, {done} ta tovarga rasm qo'shildi.")
