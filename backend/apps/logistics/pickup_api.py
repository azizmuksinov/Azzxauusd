"""Olib ketish punktlari: ommaviy ro'yxat va boshqaruv."""

from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, viewsets
from rest_framework.permissions import AllowAny

from apps.core.permissions import HasRole

from .models import PickupPoint


class PickupPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupPoint
        fields = [
            "id",
            "name",
            "address",
            "landmark",
            "hours",
            "phone",
            "latitude",
            "longitude",
            "is_active",
            "sort",
        ]


@extend_schema(tags=["checkout"])
class PickupPointListView(generics.ListAPIView):
    """Olib ketish punktlari (faol). Bo'sh ro'yxat — olib ketish taklif qilinmaydi."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    serializer_class = PickupPointSerializer
    pagination_class = None
    queryset = PickupPoint.objects.filter(is_active=True)


@extend_schema(tags=["admin: logistics"])
class PickupPointAdminViewSet(viewsets.ModelViewSet):
    """Olib ketish punktlarini boshqarish. Rol: logistics_manager."""

    permission_classes = [HasRole.of("logistics_manager")]
    serializer_class = PickupPointSerializer
    pagination_class = None
    queryset = PickupPoint.objects.all()
    http_method_names = ["get", "post", "patch", "delete"]
