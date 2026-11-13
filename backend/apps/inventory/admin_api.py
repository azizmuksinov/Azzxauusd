"""Omborchi uchun API: /api/v1/admin/... (rol: warehouse yoki admin)."""

from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.admin_api import AdminPagination
from apps.catalog.models import ProductVariant
from apps.core.permissions import HasRole

from . import services
from .models import SerialUnit, Stock, StockMovement, Warehouse

WarehouseRole = HasRole.of("warehouse")
WarehouseOrSupport = HasRole.of("warehouse", "support")


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            "id",
            "code",
            "name",
            "district",
            "address",
            "latitude",
            "longitude",
            "is_active",
            "is_sellable",
        ]


class StockSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)
    available = serializers.IntegerField(read_only=True)

    class Meta:
        model = Stock
        fields = [
            "id",
            "warehouse",
            "warehouse_code",
            "variant",
            "sku",
            "on_hand",
            "reserved",
            "available",
            "updated_at",
        ]


class SerialInputSerializer(serializers.Serializer):
    serial_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    imei1 = serializers.CharField(max_length=15, required=False, allow_null=True, default=None)
    imei2 = serializers.CharField(max_length=15, required=False, allow_null=True, default=None)


class ReceiptSerializer(serializers.Serializer):
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.filter(is_active=True))
    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all())
    qty = serializers.IntegerField(min_value=1, max_value=10000)
    serials = SerialInputSerializer(many=True, required=False, default=list)
    document = serializers.CharField(
        max_length=64, required=False, allow_blank=True, help_text="Yuk xati raqami"
    )
    comment = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class AdjustmentSerializer(serializers.Serializer):
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all())
    on_hand = serializers.IntegerField(min_value=0)
    comment = serializers.CharField(max_length=255)


class MovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = [
            "id",
            "warehouse",
            "variant",
            "delta",
            "on_hand_after",
            "reason",
            "ref_type",
            "ref_id",
            "comment",
            "created_by",
            "created_at",
        ]


class SerialUnitSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)

    class Meta:
        model = SerialUnit
        fields = [
            "id",
            "variant",
            "sku",
            "warehouse",
            "serial_number",
            "imei1",
            "imei2",
            "status",
            "received_at",
            "history",
        ]


@extend_schema(tags=["admin: inventory"])
class WarehouseViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [WarehouseRole]
    serializer_class = WarehouseSerializer
    queryset = Warehouse.objects.all()
    pagination_class = None


@extend_schema(tags=["admin: inventory"])
class StockListView(generics.ListAPIView):
    permission_classes = [WarehouseRole]
    serializer_class = StockSerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = Stock.objects.select_related("variant", "warehouse").annotate(avail=F("on_hand") - F("reserved"))
        p = self.request.query_params
        if v := p.get("warehouse"):
            qs = qs.filter(warehouse_id=v)
        if v := p.get("sku"):
            qs = qs.filter(variant__sku__icontains=v)
        if v := p.get("variant"):
            qs = qs.filter(variant_id=v)
        if v := p.get("low_stock"):
            qs = qs.filter(avail__lte=int(v))
        return qs.order_by("variant__sku", "warehouse__code")


@extend_schema(tags=["admin: inventory"])
class ReceiptView(APIView):
    permission_classes = [WarehouseRole]

    @extend_schema(request=ReceiptSerializer, responses={201: StockSerializer})
    def post(self, request):
        ser = ReceiptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        stock = services.receive(
            d["warehouse"],
            d["variant"],
            d["qty"],
            serials=[services.SerialInput(**s) for s in d["serials"]],
            user=request.user,
            ref=("receipt", d.get("document") or ""),
            comment=d["comment"],
        )
        return Response(StockSerializer(stock).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["admin: inventory"])
class AdjustmentView(APIView):
    permission_classes = [WarehouseRole]

    @extend_schema(request=AdjustmentSerializer, responses=StockSerializer)
    def post(self, request):
        ser = AdjustmentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        stock = services.adjust(
            d["warehouse"], d["variant"], d["on_hand"], user=request.user, comment=d["comment"]
        )
        return Response(StockSerializer(stock).data)


@extend_schema(tags=["admin: inventory"])
class MovementListView(generics.ListAPIView):
    permission_classes = [WarehouseRole]
    serializer_class = MovementSerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = StockMovement.objects.all()
        p = self.request.query_params
        if v := p.get("variant"):
            qs = qs.filter(variant_id=v)
        if v := p.get("warehouse"):
            qs = qs.filter(warehouse_id=v)
        if v := p.get("reason"):
            qs = qs.filter(reason=v)
        return qs


@extend_schema(tags=["admin: inventory"])
class SerialUnitListView(generics.ListAPIView):
    permission_classes = [WarehouseOrSupport]
    serializer_class = SerialUnitSerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = SerialUnit.objects.select_related("variant").order_by("-id")
        p = self.request.query_params
        if v := p.get("q"):
            qs = qs.filter(Q(serial_number__iexact=v) | Q(imei1=v) | Q(imei2=v))
        if v := p.get("status"):
            qs = qs.filter(status=v)
        if v := p.get("variant"):
            qs = qs.filter(variant_id=v)
        return qs


@extend_schema(tags=["admin: inventory"])
class SerialUnitDetailView(generics.RetrieveAPIView):
    permission_classes = [WarehouseOrSupport]
    serializer_class = SerialUnitSerializer

    def get_object(self):
        return get_object_or_404(SerialUnit.objects.select_related("variant"), pk=self.kwargs["pk"])
