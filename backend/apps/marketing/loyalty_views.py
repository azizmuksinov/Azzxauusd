"""Kun tovari, "birga arzonroq" to'plamlari va bonus: ommaviy va xodim API'lari."""

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.admin_api import AdminPagination
from apps.catalog.models import Product, ProductVariant
from apps.catalog.selectors import public_products
from apps.catalog.serializers import ProductCardSerializer
from apps.catalog.views import with_card_prefetch
from apps.core.exceptions import ApiError
from apps.core.permissions import HasRole
from apps.core.phone import InvalidPhone, normalize_phone

from . import bonus, bundles, deals
from .models import BonusEntry, Bundle, Deal

ContentRole = HasRole.of("content_manager")
AdminRole = HasRole.of("admin")


def _name(product: Product) -> str:
    return product.name.get("uz") or product.name.get("ru") or product.slug


# ------------------------------------------------------------------ kun tovari
@extend_schema(tags=["catalog"], responses=OpenApiTypes.OBJECT)
class DealListView(APIView):
    """Hozir davom etayotgan vaqtli aksiyalar: tovar kartochkasi, aksiya narxi va tugash vaqti."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        live = list(deals.live()[:12])
        products = {
            p.pk: p
            for p in with_card_prefetch(public_products().filter(pk__in=[d.variant.product_id for d in live]))
        }
        out = []
        for d in live:
            product = products.get(d.variant.product_id)
            if product is None:
                continue
            card = ProductCardSerializer(product, context={"request": request}).data
            # Kartochkadagi narx — eng arzon variantniki; aksiya boshqa variantda bo'lsa, shunisi chiqadi.
            card.update(variant_id=d.variant_id, price=str(d.price), old_price=str(d.variant.old_price or ""))
            out.append({"id": d.id, "ends_at": d.ends_at, "starts_at": d.starts_at, "product": card})
        return Response(out)


class DealSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()
    product_slug = serializers.CharField(source="variant.product.slug", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)
    current_price = serializers.DecimalField(
        source="variant.price", max_digits=14, decimal_places=2, read_only=True
    )
    state_label = serializers.CharField(source="get_state_display", read_only=True)

    class Meta:
        model = Deal
        fields = [
            "id",
            "variant",
            "sku",
            "product",
            "product_slug",
            "price",
            "current_price",
            "base_price",
            "starts_at",
            "ends_at",
            "state",
            "state_label",
            "note",
            "created_at",
        ]
        read_only_fields = ["id", "base_price", "state", "created_at"]
        extra_kwargs = {"starts_at": {"required": False, "allow_null": True}}

    def get_product(self, obj) -> str:
        return _name(obj.variant.product)


@extend_schema(tags=["admin: marketing"])
class DealAdminViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Kun tovari (vaqtli aksiya). Yaratish: variant, aksiya narxi, boshlanish (bo'sh — hozir) va tugash
    vaqti. O'chirish — aksiyani bekor qilish (narx qaytadi). Rol: content_manager."""

    permission_classes = [ContentRole]
    serializer_class = DealSerializer
    pagination_class = AdminPagination

    queryset = Deal.objects.select_related("variant__product")

    def list(self, request, *args, **kwargs):
        deals.maybe_sync()  # muddati o'tgan aksiyalar ro'yxatda "tugagan" bo'lib ko'rinsin
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        d = serializer.validated_data
        serializer.instance = deals.create(
            variant=d["variant"],
            price=d["price"],
            starts_at=d.get("starts_at"),
            ends_at=d["ends_at"],
            note=d.get("note", ""),
        )

    def perform_destroy(self, instance):
        deals.cancel(instance)


# ------------------------------------------------------------------ birga arzonroq
@extend_schema(tags=["catalog"], responses=OpenApiTypes.OBJECT)
class ProductBundlesView(APIView):
    """Shu tovar bilan birga olinsa arzonroq bo'ladigan tovarlar (chegirma qo'shimcha tovarga beriladi)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, slug):
        product = get_object_or_404(public_products(), slug=slug)
        pairs = bundles.offers(product)
        cards = {
            p.pk: ProductCardSerializer(p, context={"request": request}).data
            for p in with_card_prefetch(public_products().filter(pk__in=[e.pk for _, e in pairs]))
        }
        out = []
        for b, extra in pairs:
            if extra.pk not in cards or extra.min_price is None:
                continue
            price = bundles.price_with(b, extra.min_price)
            out.append(
                {
                    "id": b.id,
                    "discount_percent": str(b.discount_percent.normalize()),
                    "bundle_price": str(price),
                    "save": str(extra.min_price - price),
                    "product": cards[extra.pk],
                }
            )
        return Response(out)


class BundleSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    extra_name = serializers.SerializerMethodField()
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    extra_slug = serializers.CharField(source="extra.slug", read_only=True)

    class Meta:
        model = Bundle
        fields = [
            "id",
            "product",
            "product_name",
            "product_slug",
            "extra",
            "extra_name",
            "extra_slug",
            "discount_percent",
            "is_active",
            "sort",
        ]

    def get_product_name(self, obj) -> str:
        return _name(obj.product)

    def get_extra_name(self, obj) -> str:
        return _name(obj.extra)

    def validate(self, attrs):
        product = attrs.get("product", getattr(self.instance, "product", None))
        extra = attrs.get("extra", getattr(self.instance, "extra", None))
        if product and extra and product.pk == extra.pk:
            raise serializers.ValidationError({"extra": "Qo'shimcha tovar asosiy tovardan boshqa bo'lsin."})
        percent = attrs.get("discount_percent")
        if percent is not None and not (0 < percent <= 90):
            raise serializers.ValidationError({"discount_percent": "Chegirma 1% dan 90% gacha."})
        return attrs


@extend_schema(tags=["admin: marketing"])
class BundleAdminViewSet(viewsets.ModelViewSet):
    """Birga arzonroq: asosiy tovar + qo'shimcha tovar + qo'shimchaga chegirma foizi. Rol: content_manager."""

    permission_classes = [ContentRole]
    serializer_class = BundleSerializer
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        qs = Bundle.objects.select_related("product", "extra")
        if pid := self.request.query_params.get("product"):
            qs = qs.filter(product_id=pid)
        return qs


# ------------------------------------------------------------------ bonus
class BonusEntrySerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    order = serializers.CharField(source="order.number", read_only=True, default=None)

    class Meta:
        model = BonusEntry
        fields = ["id", "amount", "kind", "kind_label", "order", "note", "created_at"]


@extend_schema(tags=["me"], responses=OpenApiTypes.OBJECT)
class MyBonusView(APIView):
    """Bonus balansi, shartlar va oxirgi yozuvlar."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        entries = BonusEntry.objects.filter(user=request.user).select_related("order")[:30]
        return Response(
            {
                "enabled": bonus.enabled(),
                "balance": str(bonus.balance(request.user)),
                "earn_percent": str(bonus.earn_percent().normalize()),
                "max_pay_percent": bonus.max_pay_percent(),
                "history": BonusEntrySerializer(entries, many=True).data,
            }
        )


@extend_schema(tags=["catalog"], responses=OpenApiTypes.OBJECT)
class BonusInfoView(APIView):
    """Bonus shartlari (hamma uchun): tovar sahifasida "+N bonus" ko'rsatish uchun."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        return Response(
            {
                "enabled": bonus.enabled(),
                "earn_percent": str(bonus.earn_percent().normalize()),
                "max_pay_percent": bonus.max_pay_percent(),
            }
        )


class BonusAdjustSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    note = serializers.CharField(max_length=200)


class AdminBonusEntrySerializer(BonusEntrySerializer):
    phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta(BonusEntrySerializer.Meta):
        fields = [*BonusEntrySerializer.Meta.fields, "phone"]


@extend_schema(tags=["admin: marketing"])
class BonusAdminViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Bonus yozuvlari (`phone` bo'yicha filtr) va qo'lda tuzatish. Rol: admin."""

    permission_classes = [AdminRole]
    serializer_class = AdminBonusEntrySerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = BonusEntry.objects.select_related("user", "order")
        if q := "".join(ch for ch in self.request.query_params.get("phone", "") if ch.isdigit()):
            qs = qs.filter(user__phone__contains=q)
        return qs

    @extend_schema(request=BonusAdjustSerializer, responses={201: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"])
    def adjust(self, request):
        ser = BonusAdjustSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            phone = normalize_phone(d["phone"])
        except InvalidPhone as exc:
            raise ApiError("validation_error", str(exc)) from exc
        user = get_user_model().objects.filter(phone=phone).first()
        if user is None:
            raise ApiError("user_not_found", "Bu raqamli xaridor topilmadi.", status_code=404)
        entry = bonus.adjust(user, d["amount"], d["note"], by=request.user)
        return Response(
            {"entry": AdminBonusEntrySerializer(entry).data, "balance": str(bonus.balance(user))}, status=201
        )


class VariantPickSerializer(serializers.ModelSerializer):
    """Aksiya/to'plam formasida tovar tanlash uchun qisqa ro'yxat."""

    name = serializers.SerializerMethodField()
    product_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = ["id", "product_id", "sku", "name", "price", "old_price"]

    def get_name(self, obj) -> str:
        suffix = (obj.name_suffix or {}).get("uz") or ""
        return f"{_name(obj.product)} {suffix}".strip()


@extend_schema(tags=["admin: marketing"], responses=VariantPickSerializer(many=True))
class VariantPickView(APIView):
    """Tovar qidirish (nom, model yoki SKU bo'yicha) — aksiya va to'plam formalari uchun."""

    permission_classes = [ContentRole]

    def get(self, request):
        from django.db.models import Q

        q = request.query_params.get("q", "").strip()
        qs = ProductVariant.objects.filter(is_active=True, product__status=Product.Status.ACTIVE)
        if q:
            qs = qs.filter(
                Q(sku__icontains=q)
                | Q(product__name__uz__icontains=q)
                | Q(product__name__ru__icontains=q)
                | Q(product__model_code__icontains=q)
            )
        return Response(
            VariantPickSerializer(
                qs.select_related("product").order_by("product_id", "id")[:20], many=True
            ).data
        )
