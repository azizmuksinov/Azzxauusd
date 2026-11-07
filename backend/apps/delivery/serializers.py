from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalog.serializers import LangMixin
from apps.core.phone import normalize_phone
from apps.orders.models import Order
from apps.orders.serializers import OrderItemSerializer, StatusHistorySerializer

from . import services
from .models import (
    CashHandover,
    CodCollection,
    Courier,
    DeliveryAttempt,
    DoorPayment,
    HandoverAct,
    RouteSheet,
    RouteStop,
    Vehicle,
)


class CourierSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source="user.phone", read_only=True)
    name = serializers.SerializerMethodField()
    outstanding_cash = serializers.SerializerMethodField()

    class Meta:
        model = Courier
        fields = ["id", "phone", "name", "vehicle", "warehouse", "is_active", "outstanding_cash"]

    def get_name(self, obj) -> str:
        return str(obj)

    def get_outstanding_cash(self, obj) -> str:
        return str(services.outstanding(obj))


class CourierCreateSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    vehicle = serializers.ChoiceField(choices=Vehicle.choices, default=Vehicle.STANDARD)
    warehouse = serializers.IntegerField(required=False, allow_null=True)

    def validate_phone(self, v):
        try:
            return normalize_phone(v)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class AttemptSerializer(serializers.ModelSerializer):
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)
    courier = serializers.StringRelatedField()

    class Meta:
        model = DeliveryAttempt
        fields = ["outcome", "outcome_label", "comment", "courier", "created_at"]


class StopOrderSerializer(LangMixin, serializers.ModelSerializer):
    """Kuryer ko'radigan buyurtma: manzil, telefon, tovarlar, eshikda olinadigan summa."""

    items = OrderItemSerializer(many=True, read_only=True)
    amount_due = serializers.SerializerMethodField()
    failed_attempts = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "number",
            "status",
            "payment_method",
            "payment_status",
            "total",
            "paid_amount",
            "amount_due",
            "recipient_name",
            "recipient_phone",
            "address_snapshot",
            "address",
            "customer_comment",
            "delivery_vehicle",
            "failed_attempts",
            "items",
        ]

    def get_amount_due(self, obj) -> str:
        return str(services.amount_due_at_door(obj))

    def get_failed_attempts(self, obj) -> int:
        return services.failed_attempts(obj)

    def get_address(self, obj) -> str:
        a = obj.address_snapshot or {}
        parts = [
            self.tr(a.get("district")) if isinstance(a.get("district"), dict) else a.get("district"),
            a.get("settlement"),
            a.get("street"),
            f"{a['house']}-uy" if a.get("house") else "",
            f"{a['apartment']}-xonadon" if a.get("apartment") else "",
            f"{a['entrance']}-podyezd" if a.get("entrance") else "",
            f"{a['floor']}-qavat" if a.get("floor") else "",
        ]
        return ", ".join(p for p in parts if p)


class RouteStopSerializer(serializers.ModelSerializer):
    order = StopOrderSerializer(read_only=True)
    result_label = serializers.CharField(source="get_result_display", read_only=True)

    class Meta:
        model = RouteStop
        fields = ["id", "sequence", "result", "result_label", "started_at", "finished_at", "order"]


class RouteSheetListSerializer(serializers.ModelSerializer):
    courier = CourierSerializer(read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    stops_total = serializers.SerializerMethodField()
    stops_done = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RouteSheet
        fields = [
            "id",
            "number",
            "date",
            "status",
            "status_label",
            "courier",
            "warehouse",
            "warehouse_name",
            "stops_total",
            "stops_done",
            "comment",
            "issued_at",
            "closed_at",
        ]

    def get_stops_total(self, obj) -> int:
        return len(obj.stops.all())

    def get_stops_done(self, obj) -> int:
        return sum(1 for s in obj.stops.all() if s.result != "pending")


class RouteSheetDetailSerializer(RouteSheetListSerializer):
    stops = RouteStopSerializer(many=True, read_only=True)

    class Meta(RouteSheetListSerializer.Meta):
        fields = [*RouteSheetListSerializer.Meta.fields, "stops"]


class RouteCreateSerializer(serializers.Serializer):
    courier = serializers.PrimaryKeyRelatedField(queryset=Courier.objects.filter(is_active=True))
    warehouse = serializers.IntegerField()
    date = serializers.DateField()
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    orders = serializers.ListField(child=serializers.CharField(max_length=20), required=False, default=list)


class AddOrdersSerializer(serializers.Serializer):
    orders = serializers.ListField(child=serializers.CharField(max_length=20), min_length=1)


class InspectionSerializer(serializers.Serializer):
    packaging_intact = serializers.BooleanField(help_text="Qadoq butun")
    appearance_ok = serializers.BooleanField(help_text="Tashqi ko'rinishda nuqson yo'q")
    complete_set = serializers.BooleanField(help_text="To'liq komplekt")
    powered_on = serializers.BooleanField(
        required=False, allow_null=True, default=None, help_text="Yoqib ko'rildi"
    )


class _Geo(serializers.Serializer):
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)


class DeliverSerializer(_Geo):
    door_payment = serializers.ChoiceField(
        choices=[DoorPayment.CASH, DoorPayment.QR, DoorPayment.PREPAID], default=DoorPayment.PREPAID
    )
    inspection = InspectionSerializer()
    received_by = serializers.CharField(max_length=128)


class RefuseSerializer(_Geo):
    reason = serializers.CharField(max_length=255)


class FailSerializer(_Geo):
    outcome = serializers.ChoiceField(choices=sorted(DeliveryAttempt.Outcome.failures()))


class QrRequestSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=["payme", "click"])


class HandoverActSerializer(serializers.ModelSerializer):
    class Meta:
        model = HandoverAct
        fields = [
            "number",
            "inspection",
            "serials",
            "door_payment",
            "amount_collected",
            "received_by",
            "comment",
            "created_at",
        ]


class CodCollectionSerializer(serializers.ModelSerializer):
    order = serializers.CharField(source="order.number")
    handover = serializers.CharField(source="handover.number", default=None)

    class Meta:
        model = CodCollection
        fields = ["id", "order", "amount", "handover", "created_at"]


class CashHandoverSerializer(serializers.ModelSerializer):
    courier = serializers.StringRelatedField()
    account = serializers.StringRelatedField()
    accepted_by = serializers.StringRelatedField()
    orders_count = serializers.SerializerMethodField()

    class Meta:
        model = CashHandover
        fields = [
            "id",
            "number",
            "courier",
            "account",
            "amount",
            "orders_count",
            "accepted_by",
            "comment",
            "created_at",
        ]

    def get_orders_count(self, obj) -> int:
        return obj.collections.count()


class AcceptCashSerializer(serializers.Serializer):
    courier = serializers.PrimaryKeyRelatedField(queryset=Courier.objects.all())
    account = serializers.IntegerField()
    collection_ids = serializers.ListField(child=serializers.IntegerField(), required=False, allow_null=True)
    comment = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class StaffOrderListSerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    failed_attempts = serializers.SerializerMethodField()
    in_route = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = [
            "number",
            "status",
            "status_label",
            "payment_method",
            "payment_status",
            "total",
            "paid_amount",
            "items_count",
            "recipient_name",
            "recipient_phone",
            "district",
            "delivery_vehicle",
            "failed_attempts",
            "in_route",
            "created_at",
        ]

    def get_items_count(self, obj) -> int:
        return sum(i.qty for i in obj.items.all())

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_district(self, obj):
        return (obj.address_snapshot or {}).get("district")

    def get_failed_attempts(self, obj) -> int:
        return services.failed_attempts(obj)

    def get_in_route(self, obj) -> str | None:
        stop = next((s for s in obj.route_stops.all() if s.is_open), None)
        return stop.route.number if stop else None


class StaffOrderItemSerializer(OrderItemSerializer):
    serial_tracking = serializers.CharField(source="variant.product.serial_tracking", read_only=True)
    serials = serializers.SerializerMethodField()

    class Meta(OrderItemSerializer.Meta):
        fields = [*OrderItemSerializer.Meta.fields, "serial_tracking", "serials"]

    def get_serials(self, obj) -> list[dict]:
        return [
            {
                "id": s.serial_unit_id,
                "serial_number": s.serial_unit.serial_number,
                "imei1": s.serial_unit.imei1,
                "imei2": s.serial_unit.imei2,
            }
            for s in obj.serials.select_related("serial_unit")
        ]


class StaffOrderDetailSerializer(StopOrderSerializer):
    items = StaffOrderItemSerializer(many=True, read_only=True)
    history = StatusHistorySerializer(many=True, read_only=True)
    attempts = AttemptSerializer(source="delivery_attempts", many=True, read_only=True)
    handover_act = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta(StopOrderSerializer.Meta):
        fields = [
            *StopOrderSerializer.Meta.fields,
            "status_label",
            "subtotal",
            "delivery_fee",
            "required_prepayment",
            "cancel_reason",
            "history",
            "attempts",
            "handover_act",
            "created_at",
        ]

    def get_handover_act(self, obj) -> dict | None:
        act = getattr(obj, "handover_act", None)
        return HandoverActSerializer(act).data if act else None


class PackSerializer(serializers.Serializer):
    serials = serializers.DictField(
        child=serializers.ListField(child=serializers.IntegerField()),
        required=False,
        default=dict,
        help_text='{"<order_item_id>": [serial_unit_id, ...]} — seriyali tovarlar uchun',
    )
