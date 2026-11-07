from rest_framework import serializers

from apps.catalog.serializers import LangMixin

from .models import Order, OrderItem, OrderStatusHistory, PaymentMethod


class DeliveryOptionsRequest(serializers.Serializer):
    address_id = serializers.IntegerField()


class CheckoutRequest(serializers.Serializer):
    address_id = serializers.IntegerField()
    quote_id = serializers.UUIDField()
    lifting = serializers.BooleanField(default=False, help_text="Qavatga ko'tarish xizmati")


class PlaceOrderRequest(CheckoutRequest):
    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


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

    class Meta:
        model = Order
        fields = [
            "number",
            "status",
            "payment_method",
            "payment_status",
            "total",
            "items_count",
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

    class Meta:
        model = Order
        fields = [
            "number",
            "status",
            "payment_method",
            "payment_status",
            "subtotal",
            "discount_total",
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
