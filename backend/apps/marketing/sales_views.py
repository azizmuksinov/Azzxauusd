"""Promokodlar, "kelganda xabar bering" va 1 bosishda xarid: ommaviy va xodim API'lari."""

from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.views import client_ip
from apps.cart.services import get_cart, summarize
from apps.catalog.admin_api import AdminPagination
from apps.core.permissions import HasRole

from . import leads, promo
from .models import PromoCode, QuickOrder, StockRequest

ContentRole = HasRole.of("content_manager")
SupportRole = HasRole.of("support", "content_manager")


# --- ommaviy ---
class PromoCheckRequest(serializers.Serializer):
    code = serializers.CharField(max_length=32)


class PromoCheckResponse(serializers.Serializer):
    code = serializers.CharField()
    discount = serializers.CharField()
    subtotal = serializers.CharField()


@extend_schema(tags=["cart"])
class PromoCheckView(APIView):
    """Savatdagi tovarlar uchun promokodni tekshirish (mehmon ham). Chegirma rasmiylashtirishda qo'llanadi."""

    permission_classes = [AllowAny]

    @extend_schema(request=PromoCheckRequest, responses=PromoCheckResponse)
    def post(self, request):
        ser = PromoCheckRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        summary = summarize(get_cart(request))
        user = request.user if request.user.is_authenticated else None
        found, discount = promo.validate(ser.validated_data["code"], summary.subtotal, user)
        return Response({"code": found.code, "discount": str(discount), "subtotal": str(summary.subtotal)})


class LeadRequest(serializers.Serializer):
    variant_id = serializers.IntegerField()
    phone = serializers.CharField(max_length=24)
    name = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


class QuickOrderRequest(LeadRequest):
    qty = serializers.IntegerField(min_value=1, max_value=99, required=False, default=1)
    comment = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class LeadResponse(serializers.Serializer):
    id = serializers.IntegerField()
    phone = serializers.CharField()


@extend_schema(tags=["catalog"])
class StockRequestView(APIView):
    """ "Kelganda xabar bering": tugagan tovar uchun telefon qoldirish (ro'yxatdan o'tmasdan)."""

    permission_classes = [AllowAny]

    @extend_schema(request=LeadRequest, responses={201: LeadResponse})
    def post(self, request):
        ser = LeadRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = leads.stock_request(**ser.validated_data, user=request.user, ip=client_ip(request) or "")
        return Response({"id": obj.id, "phone": obj.phone}, status=201)


@extend_schema(tags=["orders"])
class QuickOrderView(APIView):
    """1 bosishda xarid: faqat telefon; operator qo'ng'iroq qilib manzil va to'lovni aniqlaydi."""

    permission_classes = [AllowAny]

    @extend_schema(request=QuickOrderRequest, responses={201: LeadResponse})
    def post(self, request):
        ser = QuickOrderRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = leads.quick_order(**ser.validated_data, user=request.user, ip=client_ip(request) or "")
        return Response({"id": obj.id, "phone": obj.phone}, status=201)


# --- xodim ---
class PromoCodeSerializer(serializers.ModelSerializer):
    used = serializers.SerializerMethodField()

    class Meta:
        model = PromoCode
        fields = [
            "id", "code", "kind", "value", "min_subtotal", "max_discount", "usage_limit", "once_per_customer",
            "starts_at", "ends_at", "is_active", "note", "used", "created_at",
        ]  # fmt: skip
        read_only_fields = ["id", "used", "created_at"]

    def get_used(self, obj) -> int:
        return promo.used_count(obj)

    def validate_code(self, value):
        value = value.strip().upper()
        if not value.replace("-", "").replace("_", "").isalnum():
            raise serializers.ValidationError("Kodda faqat harf, raqam, - va _ bo'lsin.")
        return value

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", PromoCode.Kind.PERCENT))
        value = attrs.get("value", getattr(self.instance, "value", None))
        if value is not None and (value <= 0 or (kind == PromoCode.Kind.PERCENT and value > 90)):
            raise serializers.ValidationError(
                {"value": "Foiz 1–90 oralig'ida, summa esa 0 dan katta bo'lsin."}
            )
        return attrs


@extend_schema(tags=["admin: marketing"])
class PromoCodeAdminViewSet(viewsets.ModelViewSet):
    """Promokodlar. `used` — bekor qilinmagan buyurtmalardagi foydalanish soni. Rol: content_manager."""

    permission_classes = [ContentRole]
    serializer_class = PromoCodeSerializer
    pagination_class = AdminPagination
    queryset = PromoCode.objects.all()
    http_method_names = ["get", "post", "patch", "delete"]


class _LeadSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()
    product_slug = serializers.CharField(source="variant.product.slug", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    available = serializers.SerializerMethodField()

    def get_product(self, obj) -> str:
        name = obj.variant.product.name
        return name.get("uz") or name.get("ru") or obj.variant.sku

    def get_available(self, obj) -> int:
        from apps.inventory.services import available_by_variant

        return available_by_variant([obj.variant_id]).get(obj.variant_id, 0)


class StockRequestSerializer(_LeadSerializer):
    class Meta:
        model = StockRequest
        fields = [
            "id", "product", "product_slug", "sku", "phone", "name", "status", "status_label", "available",
            "created_at",
        ]  # fmt: skip


class QuickOrderSerializer(_LeadSerializer):
    class Meta:
        model = QuickOrder
        fields = [
            "id", "product", "product_slug", "sku", "qty", "price", "phone", "name", "comment", "status",
            "status_label", "available", "created_at",
        ]  # fmt: skip


class LeadStatusSerializer(serializers.Serializer):
    status = serializers.CharField()


class _LeadViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [SupportRole]
    pagination_class = AdminPagination
    model = None

    def get_queryset(self):
        qs = self.model.objects.select_related("variant__product")
        if v := self.request.query_params.get("status"):
            qs = qs.filter(status=v)
        return qs

    @extend_schema(request=LeadStatusSerializer)
    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        obj = self.get_object()
        value = request.data.get("status")
        if value not in self.model.Status.values:
            raise serializers.ValidationError({"status": "Noto'g'ri holat."})
        obj.status, obj.handled_by = value, request.user
        obj.save(update_fields=["status", "handled_by", "updated_at"])
        return Response(self.get_serializer(obj).data)


@extend_schema(tags=["admin: marketing"])
class StockRequestAdminViewSet(_LeadViewSet):
    """ "Kelganda xabar bering" so'rovlari; `available` — hozirgi qoldiq. Rol: support."""

    serializer_class = StockRequestSerializer
    model = StockRequest


@extend_schema(tags=["admin: marketing"])
class QuickOrderAdminViewSet(_LeadViewSet):
    """1 bosishda xarid so'rovlari: operator mijozga qo'ng'iroq qiladi. Rol: support."""

    serializer_class = QuickOrderSerializer
    model = QuickOrder


class LeadsSummarySerializer(serializers.Serializer):
    quick_orders = serializers.IntegerField()
    stock_requests = serializers.IntegerField()


@extend_schema(tags=["admin: marketing"])
class LeadsSummaryView(APIView):
    """Menyudagi belgi uchun: yangi tez buyurtmalar va tovari kelgan "xabar bering" so'rovlari soni."""

    permission_classes = [SupportRole]

    @extend_schema(responses=LeadsSummarySerializer)
    def get(self, request):
        from apps.inventory.services import available_by_variant

        new = StockRequest.objects.filter(status=StockRequest.Status.NEW)
        stock = available_by_variant(list(new.values_list("variant_id", flat=True).distinct()))
        ready = new.filter(variant_id__in=[k for k, v in stock.items() if v > 0]).count()
        quick = QuickOrder.objects.aggregate(n=Count("id", filter=Q(status=QuickOrder.Status.NEW)))["n"]
        return Response({"quick_orders": quick, "stock_requests": ready})
