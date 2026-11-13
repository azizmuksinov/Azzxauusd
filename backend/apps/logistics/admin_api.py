"""Logistika menejeri uchun: zonalar va tariflar (/api/v1/admin/delivery-zones, /delivery-tariffs)."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets

from apps.catalog.admin_api import AdminPagination
from apps.core.permissions import HasRole

from .models import DeliveryTariff, DeliveryZone

LogisticsRole = HasRole.of("logistics_manager")


class DeliveryTariffSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryTariff
        fields = ["id", "zone", "vehicle", "max_weight_kg", "price"]


class DeliveryZoneSerializer(serializers.ModelSerializer):
    tariffs = DeliveryTariffSerializer(many=True, read_only=True)

    class Meta:
        model = DeliveryZone
        fields = [
            "id",
            "name",
            "regions",
            "districts",
            "eta_days_min",
            "eta_days_max",
            "is_active",
            "sort",
            "tariffs",
        ]

    def validate(self, attrs):
        lo = attrs.get("eta_days_min", getattr(self.instance, "eta_days_min", 1))
        hi = attrs.get("eta_days_max", getattr(self.instance, "eta_days_max", 1))
        if lo > hi:
            raise serializers.ValidationError({"eta_days_max": "eta_days_min dan kichik bo'lmasin."})
        return attrs


@extend_schema(tags=["admin: logistics"])
class DeliveryZoneViewSet(viewsets.ModelViewSet):
    permission_classes = [LogisticsRole]
    pagination_class = AdminPagination
    serializer_class = DeliveryZoneSerializer
    queryset = DeliveryZone.objects.prefetch_related("tariffs", "regions", "districts")


@extend_schema(tags=["admin: logistics"])
class DeliveryTariffViewSet(viewsets.ModelViewSet):
    permission_classes = [LogisticsRole]
    pagination_class = AdminPagination
    serializer_class = DeliveryTariffSerializer

    def get_queryset(self):
        qs = DeliveryTariff.objects.all()
        if zone := self.request.query_params.get("zone"):
            qs = qs.filter(zone_id=zone)
        return qs
