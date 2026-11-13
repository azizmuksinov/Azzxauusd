import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Cart(models.Model):
    """Foydalanuvchi savati (user) yoki mehmon savati (guest_token, X-Cart-Token sarlavhasi)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="cart"
    )
    guest_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"cart #{self.pk} ({self.user_id or 'guest'})"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.CASCADE, related_name="+")
    qty = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "variant"], name="uniq_cart_variant"),
            models.CheckConstraint(condition=Q(qty__gte=1), name="cart_qty_gte_1"),
        ]

    def __str__(self):
        return f"{self.variant_id} x{self.qty}"
