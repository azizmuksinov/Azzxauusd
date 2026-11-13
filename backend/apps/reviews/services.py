from decimal import Decimal

from django.db.models import Avg, Count

from apps.catalog.models import Product
from apps.orders.models import OrderItem, OrderStatus

from .models import Review


def has_received(user, product: Product) -> bool:
    return OrderItem.objects.filter(
        order__user=user, order__status=OrderStatus.DELIVERED, variant__product=product
    ).exists()


def refresh_rating(product: Product) -> None:
    agg = Review.objects.filter(product=product, is_published=True).aggregate(a=Avg("rating"), n=Count("id"))
    product.rating_avg = Decimal(str(round(agg["a"] or 0, 2)))
    product.rating_count = agg["n"]
    Product.objects.filter(pk=product.pk).update(
        rating_avg=product.rating_avg, rating_count=product.rating_count
    )


def distribution(product: Product) -> dict[str, int]:
    rows = Review.objects.filter(product=product, is_published=True).values("rating").annotate(n=Count("id"))
    out = {str(i): 0 for i in range(5, 0, -1)}
    for r in rows:
        out[str(r["rating"])] = r["n"]
    return out
