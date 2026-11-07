from rest_framework import serializers

from apps.catalog.selectors import stock_status
from apps.catalog.serializers import LangMixin


class CartAddSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    qty = serializers.IntegerField(min_value=1, default=1)


class CartQtySerializer(serializers.Serializer):
    qty = serializers.IntegerField(min_value=1)


class CartMergeSerializer(serializers.Serializer):
    guest_token = serializers.UUIDField()


class CartSummarySerializer(LangMixin, serializers.Serializer):
    """CartSummary obyektini JSON'ga aylantiradi."""

    def to_representation(self, summary):
        lines = []
        for line in summary.lines:
            v, p = line.variant, line.variant.product
            images = list(p.images.order_by("sort", "id")[:1])
            lines.append(
                {
                    "id": line.item.id,
                    "variant_id": v.id,
                    "sku": v.sku,
                    "product": {
                        "id": p.id,
                        "slug": p.slug,
                        "name": self.tr(p.name),
                        "is_bulky": p.is_bulky,
                        "category_slug": p.category.slug,
                    },
                    "name_suffix": self.tr(v.name_suffix),
                    "image": images[0].url if images else "",
                    "qty": line.item.qty,
                    "unit_price": str(line.unit_price),
                    "old_price": str(v.old_price) if v.old_price else None,
                    "line_total": str(line.line_total),
                    "stock_status": stock_status(line.available),
                    "max_qty": line.available,
                    "problem": line.problem,
                }
            )
        return {
            "guest_token": str(summary.cart.guest_token)
            if summary.cart and not summary.cart.user_id
            else None,
            "items": lines,
            "items_count": summary.items_count,
            "subtotal": str(summary.subtotal),
            "total_weight_kg": str(summary.total_weight_kg),
            "has_bulky": summary.bulky_items > 0,
            "can_checkout": bool(summary.lines) and not summary.has_problems,
        }
