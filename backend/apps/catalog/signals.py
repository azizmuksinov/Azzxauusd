"""Tovar o'zgarganda: search_text yangilanadi va qidiruv indeksiga yuboriladi."""

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Brand, Product, ProductVariant


def refresh_products(product_ids) -> None:
    product_ids = sorted(set(product_ids))
    for product in Product.objects.filter(pk__in=product_ids).select_related("brand", "category"):
        Product.objects.filter(pk=product.pk).update(search_text=product.build_search_text())
    if settings.SEARCH_BACKEND != "db" and product_ids:
        from .tasks import index_products_task

        transaction.on_commit(lambda: index_products_task.delay(product_ids))


@receiver(post_save, sender=Product)
def _product_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        refresh_products([instance.pk])


@receiver(post_delete, sender=Product)
def _product_deleted(sender, instance, **kwargs):
    refresh_products([instance.pk])


@receiver([post_save, post_delete], sender=ProductVariant)
def _variant_changed(sender, instance, raw=False, **kwargs):
    if not raw:
        refresh_products([instance.product_id])


@receiver(post_save, sender=Brand)
def _brand_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        refresh_products(instance.products.values_list("pk", flat=True))
