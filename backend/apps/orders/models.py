from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class OrderStatus(models.TextChoices):
    CREATED = "created", "Yaratildi"
    PAID = "paid", "To'landi"
    COD_CONFIRMED = "cod_confirmed", "Tasdiqlandi (eshikda to'lov)"
    PICKING = "picking", "Yig'ilmoqda"
    PACKED = "packed", "Qadoqlandi"
    HANDED_TO_COURIER = "handed_to_courier", "Kuryerga topshirildi"
    IN_TRANSIT = "in_transit", "Yo'lda"
    OUT_FOR_DELIVERY = "out_for_delivery", "Yetkazilmoqda"
    DELIVERED = "delivered", "Yetkazildi"
    REFUSED_AT_DOOR = "refused_at_door", "Eshik oldida rad etildi"
    RETURNED = "returned", "Omborga qaytdi"
    CANCELLED = "cancelled", "Bekor qilindi"


class PaymentMethod(models.TextChoices):
    PAYME = "payme", "Payme"
    CLICK = "click", "Click"
    UZUM = "uzum", "Uzum Bank"
    CASH = "cash", "Eshik oldida (naqd yoki QR)"
    CARD_ON_DELIVERY = "card_on_delivery", "Karta/terminal (eshik oldida)"

    @classmethod
    def online(cls) -> set[str]:
        return {cls.PAYME, cls.CLICK, cls.UZUM}

    @classmethod
    def on_delivery(cls) -> set[str]:
        return {cls.CASH, cls.CARD_ON_DELIVERY}


class PaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "To'lanmagan"
    PARTIALLY_PAID = "partially_paid", "Qisman (avans)"
    PAID = "paid", "To'langan"
    REFUND_PENDING = "refund_pending", "Qaytarish kutilmoqda"
    REFUNDED = "refunded", "Qaytarilgan"


class Order(TimeStampedModel):
    # Yaratilgandan keyin (ID asosida) to'ldiriladi; bo'sh qiymatlar unique'ga xalaqit bermasligi uchun NULL.
    number = models.CharField(max_length=20, unique=True, null=True, editable=False)  # noqa: DJ001
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.CREATED)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    payment_status = models.CharField(
        max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )

    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=14, decimal_places=2)
    lifting_fee = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    required_prepayment = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cod_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="Eshikda olinadi")

    address_snapshot = models.JSONField()
    recipient_name = models.CharField(max_length=128)
    recipient_phone = models.CharField(max_length=16)
    lifting_requested = models.BooleanField(default=False)
    delivery_provider = models.CharField(max_length=16)
    delivery_vehicle = models.CharField(max_length=10)
    delivery_eta_min = models.PositiveSmallIntegerField()
    delivery_eta_max = models.PositiveSmallIntegerField()
    delivery_quote = models.ForeignKey(
        "logistics.DeliveryQuote", null=True, on_delete=models.SET_NULL, related_name="+"
    )

    customer_comment = models.TextField(blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    language = models.CharField(max_length=8, default="uz")
    idempotency_key = models.CharField(max_length=64)
    payment_deadline = models.DateTimeField(null=True, blank=True, help_text="Onlayn to'lov shu vaqtgacha")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="uniq_order_idempotency"),
            models.CheckConstraint(condition=Q(total__gte=0), name="order_total_gte_0"),
        ]

    def __str__(self):
        return self.number or f"order #{self.pk}"

    @property
    def is_cod(self) -> bool:
        return self.payment_method in PaymentMethod.on_delivery()


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT, related_name="+")
    product_name = models.JSONField()
    variant_name = models.JSONField(default=dict, blank=True)
    sku = models.CharField(max_length=64)
    qty = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    cost_price = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, help_text="Marja hisoboti uchun"
    )
    warranty_months = models.PositiveSmallIntegerField()
    mxik_code = models.CharField(max_length=32, blank=True)
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2)
    is_bulky = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.sku} x{self.qty}"


class OrderStatusHistory(models.Model):
    class Actor(models.TextChoices):
        SYSTEM = "system", "Tizim"
        CUSTOMER = "customer", "Xaridor"
        STAFF = "staff", "Xodim"
        COURIER = "courier", "Kuryer"
        PROVIDER = "provider", "Provayder"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor_type = models.CharField(max_length=10, choices=Actor.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.from_status or '∅'} → {self.to_status}"
