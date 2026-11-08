from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.serializers import LangMixin
from apps.core.permissions import HasRole

from . import services
from .models import Banner

ContentRole = HasRole.of("content_manager")


class BannerPublicSerializer(LangMixin, serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    subtitle = serializers.SerializerMethodField()
    image = serializers.CharField(source="url", read_only=True)

    class Meta:
        model = Banner
        fields = ["id", "title", "subtitle", "image", "link", "color"]

    def get_title(self, obj) -> str:
        return self.tr(obj.title)

    def get_subtitle(self, obj) -> str:
        return self.tr(obj.subtitle)


class BannerAdminSerializer(serializers.ModelSerializer):
    url = serializers.CharField(read_only=True)
    title = serializers.JSONField()
    subtitle = serializers.JSONField(required=False)

    class Meta:
        model = Banner
        fields = [
            "id",
            "title",
            "subtitle",
            "image",
            "image_url",
            "url",
            "link",
            "color",
            "sort",
            "is_active",
            "starts_at",
            "ends_at",
        ]

    def validate_color(self, v):
        if not (len(v) == 7 and v.startswith("#")):
            raise serializers.ValidationError("#RRGGBB ko'rinishida.")
        return v


@extend_schema(tags=["marketing"])
class BannerListView(APIView):
    """Bosh sahifa bannerlari (faol va muddati kelganlari)."""

    permission_classes = [AllowAny]

    @extend_schema(responses=BannerPublicSerializer(many=True))
    def get(self, request):
        qs = Banner.live(timezone.now())[:10]
        return Response(BannerPublicSerializer(qs, many=True, context={"request": request}).data)


@extend_schema(tags=["admin: marketing"])
class BannerAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [ContentRole]
    serializer_class = BannerAdminSerializer
    queryset = Banner.objects.all()
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    pagination_class = None


class DiscountSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["apply", "remove"])
    percent = serializers.IntegerField(required=False, min_value=1, max_value=90)
    category = serializers.IntegerField(required=False, allow_null=True)
    brand = serializers.IntegerField(required=False, allow_null=True)
    products = serializers.ListField(child=serializers.IntegerField(), required=False)


@extend_schema(tags=["admin: marketing"])
class BulkDiscountView(APIView):
    """Ommaviy chegirma: kategoriya (ichki kategoriyalari bilan), brend yoki tanlangan tovarlar bo'yicha."""

    permission_classes = [ContentRole]

    @extend_schema(request=DiscountSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        ser = DiscountSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        scope = {
            "category_id": d.get("category"),
            "brand_id": d.get("brand"),
            "product_ids": d.get("products"),
        }
        if d["action"] == "apply":
            n = services.apply_discount(percent=d.get("percent") or 0, user=request.user, **scope)
        else:
            n = services.remove_discount(user=request.user, **scope)
        return Response({"variants": n})


@extend_schema(tags=["marketing"], responses=OpenApiTypes.OBJECT)
class SiteContentView(APIView):
    """Do'kon matnlari (aloqa, e'lon, bosh sahifa bo'limlari, futer, ma'lumot sahifalari) — ikki tilda."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(services.site_content())


@extend_schema(tags=["admin: marketing"])
class SiteContentAdminView(APIView):
    """Sayt matnlarini boshqarish. PUT — berilgan bo'limlar almashtiriladi."""

    permission_classes = [ContentRole]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(services.site_content())

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def put(self, request):
        from apps.core.exceptions import ApiError

        try:
            return Response(services.update_site_content(request.data))
        except ValueError as exc:
            raise ApiError("validation_error", str(exc)) from exc
