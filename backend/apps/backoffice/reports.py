"""Sotuv hisoboti (xodim paneli): davr bo'yicha savdo, eng ko'p sotilgan tovarlar, to'lov usullari,
tashlab ketilgan savatlar. Faqat o'qiydi — hech narsani o'zgartirmaydi."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Min, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart.models import CartItem
from apps.core.permissions import HasRole
from apps.orders.models import Order, OrderItem, OrderStatus

# Savdoga kirmaydigan holatlar: bekor qilingan, rad etilgan va qaytgan buyurtmalar.
LOST = [OrderStatus.CANCELLED, OrderStatus.REFUSED_AT_DOOR, OrderStatus.RETURNED]
ABANDONED_AFTER = timedelta(hours=24)
ZERO = Decimal("0")


def _money(v) -> str:
    return str((v or ZERO).quantize(Decimal("1")))


def sales_report(days: int = 30, now=None) -> dict:
    now = now or timezone.now()
    days = max(1, min(int(days), 366))
    tz = timezone.get_current_timezone()
    today = timezone.localtime(now, tz).date()
    start_day = today - timedelta(days=days - 1)
    start = timezone.make_aware(timezone.datetime.combine(start_day, timezone.datetime.min.time()), tz)

    placed = Order.objects.filter(created_at__gte=start, created_at__lte=now)
    sold = placed.exclude(status__in=LOST)

    by_day = {
        row["day"]: row
        for row in sold.annotate(day=TruncDate("created_at", tzinfo=tz))
        .values("day")
        .annotate(orders=Count("id"), revenue=Sum("total"))
    }
    daily = []
    for i in range(days):
        day = start_day + timedelta(days=i)
        row = by_day.get(day) or {}
        daily.append(
            {"date": day.isoformat(), "orders": row.get("orders", 0), "revenue": _money(row.get("revenue"))}
        )

    totals = sold.aggregate(
        orders=Count("id"),
        revenue=Sum("total"),
        goods=Sum("subtotal"),
        discounts=Sum("discount_total"),
        bonus=Sum("bonus_spent"),
        delivery=Sum(F("delivery_fee") + F("lifting_fee")),
    )
    orders_count = totals["orders"] or 0
    revenue = totals["revenue"] or ZERO

    line = ExpressionWrapper(
        F("unit_price") * F("qty"), output_field=DecimalField(max_digits=16, decimal_places=2)
    )
    cost = ExpressionWrapper(
        F("cost_price") * F("qty"), output_field=DecimalField(max_digits=16, decimal_places=2)
    )
    items = OrderItem.objects.filter(order__in=sold)
    units = items.aggregate(qty=Sum("qty"))["qty"] or 0
    with_cost = items.filter(cost_price__isnull=False).aggregate(revenue=Sum(line), cost=Sum(cost))
    top = (
        items.values("variant_id", "sku", "product_name")
        .annotate(revenue=Sum(line), sold=Sum("qty"))
        .order_by("-revenue", "sku")[:10]
    )

    first_orders = Order.objects.exclude(status__in=LOST).values("user_id").annotate(first=Min("created_at"))
    new_customers = first_orders.filter(first__gte=start).count()
    customers = sold.values("user_id").distinct().count()

    stale = CartItem.objects.filter(
        cart__updated_at__gte=start,
        cart__updated_at__lt=now - ABANDONED_AFTER,
        variant__is_active=True,
    )
    cart_value = ExpressionWrapper(
        F("variant__price") * F("qty"), output_field=DecimalField(max_digits=16, decimal_places=2)
    )
    abandoned = stale.aggregate(carts=Count("cart_id", distinct=True), value=Sum(cart_value))

    return {
        "days": days,
        "from": start_day.isoformat(),
        "to": today.isoformat(),
        "totals": {
            "orders": orders_count,
            "revenue": _money(revenue),
            "avg_check": _money(revenue / orders_count if orders_count else ZERO),
            "units": units,
            "goods": _money(totals["goods"]),
            "discounts": _money(totals["discounts"]),
            "bonus_spent": _money(totals["bonus"]),
            "delivery": _money(totals["delivery"]),
            "customers": customers,
            "new_customers": new_customers,
            "delivered": placed.filter(status=OrderStatus.DELIVERED).count(),
            "cancelled": placed.filter(status__in=LOST).count(),
            "pickup": sold.filter(delivery_provider="pickup").count(),
            # Tannarxi kiritilgan tovarlar bo'yicha (kiritilmaganlari hisobga kirmaydi).
            "gross_profit": _money((with_cost["revenue"] or ZERO) - (with_cost["cost"] or ZERO))
            if with_cost["cost"] is not None
            else None,
        },
        "daily": daily,
        "top_products": [
            {
                "variant_id": r["variant_id"],
                "sku": r["sku"],
                "name": (r["product_name"] or {}).get("uz")
                or (r["product_name"] or {}).get("ru")
                or r["sku"],
                "qty": r["sold"],
                "revenue": _money(r["revenue"]),
            }
            for r in top
        ],
        "payment_methods": [
            {"code": r["payment_method"], "orders": r["orders"], "revenue": _money(r["revenue"])}
            for r in sold.values("payment_method")
            .annotate(orders=Count("id"), revenue=Sum("total"))
            .order_by("-revenue")
        ],
        "statuses": [
            {"code": r["status"], "orders": r["orders"]}
            for r in placed.values("status").annotate(orders=Count("id")).order_by("-orders")
        ],
        "abandoned_carts": {"carts": abandoned["carts"] or 0, "value": _money(abandoned["value"])},
    }


@extend_schema(tags=["admin: reports"])
class SalesReportView(APIView):
    """Sotuv hisoboti. `days` — oxirgi necha kun (1–366, standart 30). Rol: finance (va admin)."""

    permission_classes = [HasRole.of("finance")]

    @extend_schema(parameters=[OpenApiParameter("days", int)], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        try:
            days = int(request.query_params.get("days") or 30)
        except ValueError:
            days = 30
        return Response(sales_report(days))
