"""AI kartochkalar API: /api/v1/admin/ai-cards/... (rol: content_manager)."""

from django.db.models import Count, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.admin_api import AdminPagination
from apps.core.exceptions import ApiError
from apps.core.permissions import HasRole

from . import services
from .models import CardBatch, CardDraft

ContentRole = HasRole.of("content_manager")


class DraftPagination(AdminPagination):
    """Bir fayl 500 qatorgacha — kartochkalar bitta sahifada ko'rsatilsin."""

    max_page_size = 500


class BatchSerializer(serializers.ModelSerializer):
    counts = serializers.SerializerMethodField()

    class Meta:
        model = CardBatch
        fields = [
            "id",
            "file_name",
            "columns",
            "rows_total",
            "currency",
            "usd_rate",
            "markup_percent",
            "counts",
            "created_at",
        ]

    def get_counts(self, obj) -> dict:
        return {s: getattr(obj, f"n_{s}", None) or 0 for s in CardDraft.Status.values}


class DraftListSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    product_slug = serializers.CharField(source="product.slug", default=None, read_only=True)
    image = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    cost_uzs = serializers.SerializerMethodField()
    suggested_price = serializers.SerializerMethodField()

    def get_image(self, obj) -> str:
        return next(iter(obj.result.get("images") or []), "")

    def get_category(self, obj) -> str:
        """Tanlangan kategoriya slug'i yoki "+ Yangi nom" (AI taklifi), bo'lmasa bo'sh."""
        r = obj.result or {}
        if r.get("category_slug"):
            return r["category_slug"]
        nc = r.get("new_category") or {}
        return f"+ {nc['name']['uz']}" if nc.get("name") else ""

    def get_cost_uzs(self, obj) -> str | None:
        v = services.cost_in_uzs(obj)
        return str(v) if v is not None else None

    def get_suggested_price(self, obj) -> str | None:
        """Foyda foizi bo'yicha sotuv narxi (so'm)."""
        v = services.suggested_price(obj)
        return str(v) if v is not None else None

    class Meta:
        model = CardDraft
        fields = [
            "id",
            "batch",
            "row_number",
            "query",
            "supplier_sku",
            "purchase_price",
            "qty",
            "status",
            "status_label",
            "name",
            "product_slug",
            "image",
            "category",
            "cost_uzs",
            "suggested_price",
            "updated_at",
        ]

    def get_name(self, obj) -> str:
        return (obj.result.get("name") or {}).get("uz", "")


class DraftSerializer(DraftListSerializer):
    class Meta(DraftListSerializer.Meta):
        fields = [
            *DraftListSerializer.Meta.fields,
            "raw",
            "result",
            "warnings",
            "error",
            "model_used",
        ]


class CurrencySerializer(serializers.Serializer):
    currency = serializers.ChoiceField(choices=["UZS", "USD", ""])


class CategorizeSerializer(serializers.Serializer):
    only_missing = serializers.BooleanField(
        default=True, help_text="Faqat kategoriyasizlar (aks holda hammasi)"
    )


class FromUrlSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=1000)


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    currency = serializers.ChoiceField(choices=["UZS", "USD", ""], required=False)
    usd_rate = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=1, required=False, allow_null=True
    )
    markup_percent = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=0, max_value=1000, required=False, allow_null=True
    )


class PreviewSerializer(serializers.Serializer):
    file = serializers.FileField()


class BatchSettingsSerializer(serializers.Serializer):
    currency = serializers.ChoiceField(choices=["UZS", "USD", ""], required=False)
    usd_rate = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=1, required=False, allow_null=True
    )
    markup_percent = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=0, max_value=1000, required=False, allow_null=True
    )


class PublishManySerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False, max_length=500)
    publish = serializers.BooleanField(default=True)


class EditSerializer(serializers.Serializer):
    """Xodim tahriri: faqat berilgan maydonlar almashtiriladi."""

    brand = serializers.CharField(required=False, allow_blank=True)
    model_code = serializers.CharField(required=False, allow_blank=True)
    category_slug = serializers.CharField(required=False, allow_blank=True)
    name = serializers.DictField(child=serializers.CharField(allow_blank=True), required=False)
    description = serializers.DictField(child=serializers.CharField(allow_blank=True), required=False)
    warranty_months = serializers.IntegerField(required=False, allow_null=True)
    weight_kg = serializers.FloatField(required=False, allow_null=True)
    is_bulky = serializers.BooleanField(required=False)
    attributes = serializers.DictField(required=False, help_text="Birlashtiriladi; null — o'chirish")
    images = serializers.ListField(child=serializers.URLField(), required=False)
    new_category = serializers.DictField(
        required=False, allow_null=True, help_text="{name:{uz,ru}, parent_slug}"
    )
    specs = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="[{group:{uz,ru}, name:{uz,ru}, value:{uz,ru}}]",
    )


class ApproveSerializer(serializers.Serializer):
    price = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    old_price = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    sku = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    publish = serializers.BooleanField(default=True)


@extend_schema(tags=["admin: ai-cards"])
class BatchViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Ta'minotchi faylini yuklash va Gemini bilan qatorma-qator to'ldirish."""

    permission_classes = [ContentRole]
    serializer_class = BatchSerializer
    pagination_class = AdminPagination
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        return CardBatch.objects.annotate(
            **{f"n_{s}": Count("drafts", filter=Q(drafts__status=s)) for s in CardDraft.Status.values}
        ).order_by("-created_at", "-id")

    @extend_schema(request={"multipart/form-data": UploadSerializer}, responses={201: BatchSerializer})
    def create(self, request):
        ser = UploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        f = d["file"]
        if f.size > 5 * 1024 * 1024:
            raise ApiError("file_too_large", "Fayl 5 MB dan katta bo'lmasin.")
        batch = services.create_batch(
            file_name=f.name,
            data=f.read(),
            user=request.user,
            currency=d.get("currency"),
            usd_rate=d.get("usd_rate"),
            markup_percent=d.get("markup_percent"),
        )
        return Response(BatchSerializer(self.get_queryset().get(pk=batch.pk)).data, status=201)

    @extend_schema(request={"multipart/form-data": PreviewSerializer}, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def preview(self, request):
        """Fayl tanlanganda (yuklashdan oldin): tovarlar soni, ustunlar, narx valyutasi, birinchi qatorlar."""
        ser = PreviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        f = ser.validated_data["file"]
        if f.size > 5 * 1024 * 1024:
            raise ApiError("file_too_large", "Fayl 5 MB dan katta bo'lmasin.")
        return Response(services.preview_file(f.read()))

    @extend_schema(request=BatchSettingsSerializer, responses=BatchSerializer)
    @action(
        detail=True, methods=["patch"], parser_classes=[JSONParser], url_path="settings", url_name="settings"
    )
    def batch_settings(self, request, pk=None):
        """Valyuta, dollar kursi va foyda foizi (sotuv narxlari shundan hisoblanadi)."""
        ser = BatchSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        CardBatch.objects.filter(pk=self.get_object().pk).update(**ser.validated_data)
        return Response(BatchSerializer(self.get_queryset().get(pk=pk)).data)

    @extend_schema(request=PublishManySerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], parser_classes=[JSONParser])
    def publish(self, request, pk=None):
        """Belgilangan kartochkalarni bir yo'la nashr qilish (narx — foyda foizi bo'yicha)."""
        ser = PublishManySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        out = services.publish_many(self.get_object(), d["ids"], user=request.user, publish=d["publish"])
        return Response(out)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"], url_path="export")
    def export(self, request, pk=None):
        """Yuklamani JSON zaxira sifatida (AI natijalari bilan) — keyin `import` bilan tiklanadi."""
        return Response(services.export_batch(self.get_object()))

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: BatchSerializer})
    @action(
        detail=False,
        methods=["post"],
        parser_classes=[JSONParser, MultiPartParser],
        url_path="import",
        url_name="import",
    )
    def import_(self, request):
        """Zaxiradan tiklash: JSON tanasi yoki `file` (export natijasi). AI so'rovi sarflanmaydi."""
        import json as _json

        data = request.data
        if "file" in request.FILES:
            try:
                data = _json.loads(request.FILES["file"].read().decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise ApiError("bad_backup", "Fayl JSON emas.") from exc
        batch = services.import_batch(data, user=request.user)
        return Response(BatchSerializer(self.get_queryset().get(pk=batch.pk)).data, status=201)

    @extend_schema(request=CurrencySerializer, responses=BatchSerializer)
    @action(detail=True, methods=["post"], parser_classes=[JSONParser], url_path="currency")
    def set_currency(self, request, pk=None):
        """Fayldagi narx valyutasini qo'lda belgilash (sarlavhadan aniqlanmagan bo'lsa)."""
        ser = CurrencySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        CardBatch.objects.filter(pk=self.get_object().pk).update(currency=ser.validated_data["currency"])
        return Response(BatchSerializer(self.get_queryset().get(pk=pk)).data)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], parser_classes=[])
    def autofix(self, request, pk=None):
        """Muammoli kartochkalarni avto-tuzatish (rasm, kategoriya, xato) — 5 tadan.

        UI `remaining` 0 bo'lguncha chaqiradi.
        """
        try:
            out = services.autofix_batch(self.get_object())
        except services.client.AiError as exc:
            raise ApiError(
                f"ai_{exc.code}", exc.message, status_code=429 if exc.code == "rate_limited" else 503
            ) from exc
        return Response({**out, "usage": services.usage()})

    @extend_schema(request=CategorizeSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], parser_classes=[JSONParser])
    def categorize(self, request, pk=None):
        """Kartochkalar kategoriyasini AI bilan aniqlash (40 tasi bitta so'rovda).

        Mos kategoriya bo'lmasa — yangisi taklif qilinadi (nashrda yaratiladi).
        """
        ser = CategorizeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            stats = services.categorize_batch(
                self.get_object(), only_missing=ser.validated_data["only_missing"]
            )
        except services.client.AiError as exc:
            raise ApiError(
                f"ai_{exc.code}", exc.message, status_code=429 if exc.code == "rate_limited" else 503
            ) from exc
        return Response({**stats, "usage": services.usage()})

    @extend_schema(request=None, responses=BatchSerializer)
    @action(detail=True, methods=["post"], parser_classes=[], url_path="retry-failed")
    def retry_failed(self, request, pk=None):
        """Xato bo'lgan qatorlarni qayta navbatga qo'yish."""
        services.requeue_failed(self.get_object())
        return Response(BatchSerializer(self.get_queryset().get(pk=pk)).data)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], parser_classes=[])
    def process(self, request, pk=None):
        """Navbatdagi bitta qatorni Gemini orqali to'ldiradi. UI `remaining` 0 bo'lguncha chaqiradi."""
        batch = self.get_object()
        draft = services.next_pending(batch)
        if draft is not None:
            draft = services.generate(draft)
        remaining = batch.drafts.filter(status=CardDraft.Status.PENDING).count()
        return Response(
            {
                "draft": DraftListSerializer(draft).data if draft else None,
                "remaining": remaining,
                "usage": services.usage(),
            }
        )


@extend_schema(tags=["admin: ai-cards"])
class DraftViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Kartochkalar: ko'rish, tahrirlash, nashr qilish, rad etish, qayta yaratish.

    Filtr: `batch`, `status`.
    """

    permission_classes = [ContentRole]
    pagination_class = DraftPagination

    def get_serializer_class(self):
        return DraftListSerializer if self.action == "list" else DraftSerializer

    def get_queryset(self):
        qs = CardDraft.objects.select_related("product", "batch")
        p = self.request.query_params
        if p.get("batch"):
            qs = qs.filter(batch_id=p["batch"])
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        return qs

    @extend_schema(request=FromUrlSerializer, responses={201: DraftSerializer})
    @action(detail=False, methods=["post"], url_path="from-url")
    def from_url(self, request):
        """Boshqa do'kon (Uzum, Ozon, Yandex Market...) havolasidan ikki tilli kartochka (qoralama)."""
        ser = FromUrlSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        draft = services.create_from_url(ser.validated_data["url"], user=request.user)
        return Response(DraftSerializer(draft).data, status=201)

    @extend_schema(request=EditSerializer, responses=DraftSerializer)
    def partial_update(self, request, pk=None):
        ser = EditSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        draft = services.update_result(self.get_object(), ser.validated_data)
        return Response(DraftSerializer(draft).data)

    @extend_schema(request=ApproveSerializer, responses=DraftSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        ser = ApproveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        draft = self.get_object()
        services.approve(
            draft,
            user=request.user,
            price=d["price"],
            old_price=d.get("old_price"),
            sku=d["sku"],
            publish=d["publish"],
        )
        return Response(DraftSerializer(CardDraft.objects.get(pk=draft.pk)).data)

    @extend_schema(request=None, responses=DraftSerializer)
    @action(detail=True, methods=["post"], url_path="autofix")
    def autofix(self, request, pk=None):
        """Bitta kartochkani avto-tuzatish: rasm topish, kategoriya aniqlash, xato bo'lsa qayta yaratish."""
        try:
            services.autofix(self.get_object())
        except services.client.AiError as exc:
            raise ApiError(
                f"ai_{exc.code}", exc.message, status_code=429 if exc.code == "rate_limited" else 503
            ) from exc
        return Response(DraftSerializer(CardDraft.objects.get(pk=pk)).data)

    @extend_schema(request=None, responses=DraftSerializer)
    @action(detail=True, methods=["post"], url_path="create-category")
    def create_category(self, request, pk=None):
        """AI taklif qilgan yangi kategoriyani hozir qo'shish va kartochkaga tanlash."""
        return Response(DraftSerializer(services.create_proposed_category(self.get_object())).data)

    @extend_schema(request=None, responses=DraftSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return Response(DraftSerializer(services.reject(self.get_object(), user=request.user)).data)

    @extend_schema(request=None, responses=DraftSerializer)
    @action(detail=True, methods=["post"])
    def regenerate(self, request, pk=None):
        draft = services.generate(services.reset(self.get_object()))
        return Response(DraftSerializer(draft).data)


class AiSettingsSerializer(serializers.Serializer):
    daily_limit = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    provider_order = serializers.ListField(
        child=serializers.CharField(max_length=32), required=False, help_text="AI xizmatlari tartibi"
    )
    usd_rate = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=1,
        allow_null=True,
        required=False,
        help_text="1 USD = ? so'm",
    )


@extend_schema(tags=["admin: ai-cards"])
class AiSettingsView(APIView):
    """AI provayder, model, bugungi so'rovlar va kunlik limit. Provayder va kalit — env/secret'da."""

    permission_classes = [ContentRole]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(services.usage())

    @extend_schema(request=AiSettingsSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request):
        from apps.core.settings_registry import set_setting

        ser = AiSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if "daily_limit" in d:
            set_setting("ai_cards_daily_limit", d["daily_limit"], user=request.user)
        if "usd_rate" in d:
            set_setting("usd_uzs_rate", d["usd_rate"], user=request.user)
        if "provider_order" in d:
            set_setting("ai_provider_order", ",".join(d["provider_order"]) or None, user=request.user)
        return Response(services.usage())


@extend_schema(tags=["admin: ai-cards"], request=None, responses=OpenApiTypes.OBJECT)
class FindImagesView(APIView):
    """Rasmsiz tovarga AI (internet qidiruvi) orqali rasm topib yuklash. Har bosish — 1 ta AI so'rov."""

    permission_classes = [ContentRole]

    def post(self, request, product_id):
        from django.shortcuts import get_object_or_404

        from apps.catalog.models import Product

        product = get_object_or_404(Product, pk=product_id)
        if product.images.exists():
            raise ApiError(
                "has_images", "Tovarda rasm bor — avval o'chiring yoki qo'lda qo'shing.", status_code=409
            )
        try:
            n = services.find_images(product)
        except services.client.AiError as exc:
            status = 429 if exc.code == "rate_limited" else 503
            raise ApiError(f"ai_{exc.code}", exc.message, status_code=status) from exc
        return Response({"images": n, "usage": services.usage()})


@extend_schema(tags=["admin: ai-cards"], request=None, responses=OpenApiTypes.OBJECT)
class AiCheckView(APIView):
    """Ulangan AI xizmatlarini tekshirish: ishlaydimi, javob vaqti, haqiqiy limitlar (har biriga 1 so'rov)."""

    permission_classes = [ContentRole]

    def post(self, request):
        return Response({"providers": services.check_providers(), "usage": services.usage()})


class MarketPriceSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=200, help_text="Brend va model, masalan: Premier PRM-G60-E31B")


@extend_schema(tags=["admin: ai-cards"], request=MarketPriceSerializer, responses=OpenApiTypes.OBJECT)
class MarketPriceView(APIView):
    """O'zbekiston do'konlaridagi narxlar: eng past / o'rtacha / eng yuqori va tavsiya.

    AI limiti sarflanmaydi.
    """

    permission_classes = [ContentRole]

    def post(self, request):
        from .market import market_price

        ser = MarketPriceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(market_price(ser.validated_data["query"]))
