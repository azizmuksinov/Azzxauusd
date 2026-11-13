from rest_framework import serializers

from apps.catalog.serializers import LangMixin

from .models import Order, OrderItem, OrderStatusHistory, PaymentMethod


class DeliveryOptionsRequest(serializers.Serializer):
    address_id = serializers.IntegerField()


class CheckoutRequest(serializers.Serializer):
    """Yetkazish: `address_id` + `quote_id`. Olib ketish: `pickup_point_id` (manzil va quote kerak emas)."""

    address_id = serializers.IntegerField(required=False, allow_null=True)
    quote_id = serializers.UUIDField(required=False, allow_null=True)
    pickup_point_id = serializers.IntegerField(required=False, allow_null=True)
    lifting = serializers.BooleanField(default=False, help_text="Qavatga ko'tarish xizmati")
    promo_code = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    use_bonus = serializers.BooleanField(
        default=False, help_text="Bonus bilan to'lash (mumkin bo'lgan eng ko'pi)"
    )

    def validate(self, attrs):
        if attrs.get("pickup_point_id"):
            if attrs.get("lifting"):
                raise serializers.ValidationError({"lifting": "Olib ketishda ko'tarish xizmati yo'q."})
        elif not (attrs.get("address_id") and attrs.get("quote_id")):
            raise serializers.ValidationError(
                {"address_id": "Yetkazish manzili va narxini (quote_id) yoki olib ketish punktini tanlang."}
            )
        return attrs


class PlaceOrderRequest(CheckoutRequest):
    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    recipient_name = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    recipient_phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")


class TrackRequest(serializers.Serializer):
    number = serializers.CharField(max_length=20)
    phone = serializers.CharField(max_length=32)


class CancelRequest(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


def money(v) -> str | None:
    return None if v is None else str(v)


class OrderItemSerializer(LangMixin, serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    variant_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "variant_id",
            "sku",
            "name",
            "variant_name",
            "qty",
            "unit_price",
            "line_total",
            "warranty_months",
            "is_bulky",
        ]

    def get_name(self, obj) -> str:
        return self.tr(obj.product_name)

    def get_variant_name(self, obj) -> str:
        return self.tr(obj.variant_name)


class StatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ["from_status", "to_status", "actor_type", "note", "created_at"]


class OrderListSerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()
    is_pickup = serializers.BooleanField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "number",
            "status",
            "payment_method",
            "payment_status",
            "total",
            "items_count",
            "is_pickup",
            "delivery_eta_min",
            "delivery_eta_max",
            "created_at",
        ]

    def get_items_count(self, obj) -> int:
        return sum(i.qty for i in obj.items.all())


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    history = StatusHistorySerializer(many=True, read_only=True)
    can_cancel = serializers.SerializerMethodField()
    amount_to_pay_online = serializers.SerializerMethodField()
    is_pickup = serializers.BooleanField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "number",
            "status",
            "payment_method",
            "payment_status",
            "subtotal",
            "discount_total",
            "promo_code",
            "bonus_spent",
            "bonus_earned",
            "is_pickup",
            "delivery_fee",
            "lifting_fee",
            "total",
            "required_prepayment",
            "paid_amount",
            "refund_due",
            "refunded_amount",
            "cod_amount",
            "amount_to_pay_online",
            "payment_deadline",
            "address_snapshot",
            "recipient_name",
            "recipient_phone",
            "lifting_requested",
            "delivery_provider",
            "delivery_eta_min",
            "delivery_eta_max",
            "customer_comment",
            "cancel_reason",
            "can_cancel",
            "items",
            "history",
            "created_at",
        ]

    def get_can_cancel(self, obj) -> bool:
        from .state import CUSTOMER_CANCELLABLE

        return obj.status in CUSTOMER_CANCELLABLE

    def get_amount_to_pay_online(self, obj) -> str:
        return str(max(obj.required_prepayment - obj.paid_amount, 0))


class TrackedOrderSerializer(LangMixin, serializers.ModelSerializer):
    """Tizimga kirmasdan kuzatish: faqat holat va tarkib (manzil, ism kabi shaxsiy ma'lumotlarsiz)."""

    items = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    pickup = serializers.SerializerMethodField()
    is_pickup = serializers.BooleanField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "number",
            "status",
            "payment_status",
            "total",
            "is_pickup",
            "pickup",
            "delivery_eta_min",
            "delivery_eta_max",
            "items",
            "history",
            "created_at",
        ]

    def get_items(self, obj) -> list[dict]:
        return [{"name": self.tr(i.product_name), "qty": i.qty} for i in obj.items.all()]

    def get_history(self, obj) -> list[dict]:
        return [{"status": h.to_status, "at": h.created_at} for h in obj.history.all()]

    def get_pickup(self, obj) -> dict | None:
        if not obj.is_pickup:
            return None
        snap = obj.address_snapshot or {}
        return {k: snap.get(k, "") for k in ("name", "address", "landmark", "hours", "phone")}
