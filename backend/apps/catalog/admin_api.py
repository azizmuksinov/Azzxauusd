"""Kontent menejeri uchun API: /api/v1/admin/... (rol: content_manager yoki admin)."""

from django.db import transaction
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.core.permissions import HasRole

from .importer import build_template
from .models import (
    Attribute,
    AttributeOption,
    AttributeValue,
    Brand,
    Category,
    CategoryAttribute,
    PriceHistory,
    Product,
    ProductImage,
    ProductImport,
    ProductVariant,
)
from .services import change_price

ContentManager = HasRole.of("content_manager")


class AdminPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def i18n_field(**kwargs):
    return serializers.JSONField(help_text='{"uz": "...", "uz_cyrl": "...", "ru": "..."}', **kwargs)


def validate_i18n(value, required=True):
    if not isinstance(value, dict):
        raise serializers.ValidationError("Obyekt bo'lishi kerak: {uz, uz_cyrl, ru}")
    extra = set(value) - {"uz", "uz_cyrl", "ru"}
    if extra:
        raise serializers.ValidationError(f"Noma'lum til kalitlari: {', '.join(sorted(extra))}")
    if required and not value.get("uz"):
        raise serializers.ValidationError("uz (lotin) qiymati majburiy")
    return value


# --- serializers ---
class CategoryAdminSerializer(serializers.ModelSerializer):
    name = i18n_field()
    attribute_ids = serializers.PrimaryKeyRelatedField(
        source="attributes", many=True, queryset=Attribute.objects.all(), required=False
    )

    class Meta:
        model = Category
        fields = ["id", "parent", "slug", "name", "icon", "sort", "is_active", "attribute_ids"]

    def validate_name(self, v):
        return validate_i18n(v)

    def validate_parent(self, parent):
        if parent and self.instance:
            node = parent
            while node:
                if node.pk == self.instance.pk:
                    raise serializers.ValidationError("Kategoriya o'zining ichiga joylashtirilmaydi.")
                node = node.parent
        return parent

    @transaction.atomic
    def _save_attrs(self, category, attrs):
        if attrs is None:
            return
        CategoryAttribute.objects.filter(category=category).exclude(attribute__in=attrs).delete()
        for i, a in enumerate(attrs):
            CategoryAttribute.objects.update_or_create(category=category, attribute=a, defaults={"sort": i})

    def create(self, validated):
        attrs = validated.pop("attributes", None)
        obj = super().create(validated)
        self._save_attrs(obj, attrs)
        return obj

    def update(self, instance, validated):
        attrs = validated.pop("attributes", None)
        obj = super().update(instance, validated)
        self._save_attrs(obj, attrs)
        return obj


class BrandAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "slug", "name", "logo", "is_active"]


class AttributeOptionAdminSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    value = i18n_field()

    class Meta:
        model = AttributeOption
        fields = ["id", "code", "value", "sort"]


class AttributeAdminSerializer(serializers.ModelSerializer):
    name = i18n_field()
    group_name = i18n_field(required=False)
    options = AttributeOptionAdminSerializer(many=True, required=False)

    class Meta:
        model = Attribute
        fields = [
            "id",
            "code",
            "name",
            "group_name",
            "data_type",
            "unit",
            "is_filterable",
            "is_comparable",
            "sort",
            "options",
        ]

    def validate_name(self, v):
        return validate_i18n(v)

    def validate(self, attrs):
        dt = attrs.get("data_type", getattr(self.instance, "data_type", None))
        if attrs.get("options") and dt != Attribute.DataType.ENUM:
            raise serializers.ValidationError({"options": "Variantlar faqat enum turida bo'ladi."})
        return attrs

    @transaction.atomic
    def _save_options(self, attr, options):
        if options is None:
            return
        keep = []
        for i, o in enumerate(options):
            obj, _ = AttributeOption.objects.update_or_create(
                attribute=attr, code=o["code"], defaults={"value": o["value"], "sort": o.get("sort", i)}
            )
            keep.append(obj.pk)
        stale = AttributeOption.objects.filter(attribute=attr).exclude(pk__in=keep)
        if AttributeValue.objects.filter(option__in=stale).exists():
            raise serializers.ValidationError({"options": "Ishlatilayotgan variantni o'chirib bo'lmaydi."})
        stale.delete()

    def create(self, validated):
        options = validated.pop("options", None)
        obj = super().create(validated)
        self._save_options(obj, options)
        return obj

    def update(self, instance, validated):
        options = validated.pop("options", None)
        obj = super().update(instance, validated)
        self._save_options(obj, options)
        return obj


class AttributeValueInputSerializer(serializers.Serializer):
    """Misollar: {"code": "screen_size", "value": 55}, {"code": "color", "value": "black"},
    {"code": "smart_tv", "value": true}. value=null — qiymatni o'chiradi."""

    code = serializers.SlugField()
    value = serializers.JSONField(allow_null=True)
    variant_id = serializers.IntegerField(required=False, allow_null=True)


def _attr_kwargs(attr: Attribute, value) -> dict:
    dt = attr.data_type
    if dt == Attribute.DataType.ENUM:
        opt = attr.options.filter(code=value).first()
        if not opt:
            raise serializers.ValidationError({"attributes": f"{attr.code}: noma'lum variant '{value}'"})
        return {"option": opt, "value_number": None, "value_text": None, "value_bool": None}
    if dt == Attribute.DataType.NUMBER:
        try:
            from decimal import Decimal

            return {
                "option": None,
                "value_number": Decimal(str(value)),
                "value_text": None,
                "value_bool": None,
            }
        except Exception as exc:
            raise serializers.ValidationError({"attributes": f"{attr.code}: son kerak"}) from exc
    if dt == Attribute.DataType.BOOL:
        if not isinstance(value, bool):
            raise serializers.ValidationError({"attributes": f"{attr.code}: true/false kerak"})
        return {"option": None, "value_number": None, "value_text": None, "value_bool": value}
    text = value if isinstance(value, dict) else {"uz": str(value)}
    return {"option": None, "value_number": None, "value_text": text, "value_bool": None}


class VariantAdminSerializer(serializers.ModelSerializer):
    name_suffix = i18n_field(required=False)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product",
            "sku",
            "barcode",
            "name_suffix",
            "price",
            "old_price",
            "cost_price",
            "weight_kg",
            "length_cm",
            "width_cm",
            "height_cm",
            "is_active",
            "sort",
        ]

    def validate(self, attrs):
        price = attrs.get("price", getattr(self.instance, "price", None))
        old = attrs.get("old_price", getattr(self.instance, "old_price", None))
        if old is not None and price is not None and old <= price:
            raise serializers.ValidationError({"old_price": "Eski narx joriy narxdan katta bo'lishi kerak."})
        if self.instance and ("price" in attrs or "old_price" in attrs):
            raise serializers.ValidationError(
                {"price": "Narx /admin/variants/{id}/price orqali o'zgartiriladi."}
            )
        return attrs

    def create(self, validated):
        variant = super().create(validated)
        PriceHistory.objects.create(
            variant=variant,
            price=variant.price,
            old_price=variant.old_price,
            source=PriceHistory.Source.MANUAL,
            changed_by=self.context["request"].user,
        )
        return variant


class ProductImageAdminSerializer(serializers.ModelSerializer):
    url = serializers.CharField(read_only=True)

    class Meta:
        model = ProductImage
        fields = ["id", "product", "variant", "file", "external_url", "alt", "sort", "url"]

    def validate(self, attrs):
        if not attrs.get("file") and not attrs.get("external_url") and not self.instance:
            raise serializers.ValidationError("file yoki external_url kerak.")
        variant = attrs.get("variant")
        if variant and variant.product_id != attrs.get("product", getattr(self.instance, "product", None)).id:
            raise serializers.ValidationError({"variant": "Variant boshqa tovarga tegishli."})
        return attrs


class ProductAdminSerializer(serializers.ModelSerializer):
    name = i18n_field()
    description = i18n_field(required=False)
    attributes = AttributeValueInputSerializer(many=True, required=False, write_only=True)
    attribute_values = serializers.SerializerMethodField()
    variants = VariantAdminSerializer(many=True, read_only=True)
    image = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "category",
            "brand",
            "slug",
            "name",
            "description",
            "model_code",
            "video_url",
            "status",
            "warranty_months",
            "is_bulky",
            "serial_tracking",
            "mxik_code",
            "package_code",
            "vat_percent",
            "rating_avg",
            "rating_count",
            "attributes",
            "attribute_values",
            "variants",
            "image",
            "stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["rating_avg", "rating_count"]
        extra_kwargs = {"slug": {"required": False}}

    def get_image(self, obj) -> str:
        first = next(iter(obj.images.all()), None)
        return first.url if first else ""

    def get_stock(self, obj) -> dict:
        """{variant_id: bo'sh qoldiq} — barcha sotuvdagi omborlar bo'yicha."""
        from apps.inventory.services import available_by_variant

        return {str(k): v for k, v in available_by_variant([v.id for v in obj.variants.all()]).items()}

    def validate_name(self, v):
        return validate_i18n(v)

    def validate(self, attrs):
        status_ = attrs.get("status", getattr(self.instance, "status", None))
        # Tekshiruv faqat sotuvga chiqarishda (allaqachon sotuvdagi tovarni tahrirlashni bloklamaydi).
        becomes_active = (
            status_ == Product.Status.ACTIVE and getattr(self.instance, "status", None) != status_
        )
        if becomes_active:
            mxik = attrs.get("mxik_code", getattr(self.instance, "mxik_code", ""))
            if not mxik:
                raise serializers.ValidationError(
                    {"mxik_code": "Sotuvga chiqarish uchun MXIK kodi majburiy (fiskal chek)."}
                )
        return attrs

    def get_attribute_values(self, obj) -> list[dict]:
        out = []
        for av in obj.attribute_values.all():
            if av.option_id:
                raw = av.option.code
            elif av.value_number is not None:
                raw = float(av.value_number)
            elif av.value_bool is not None:
                raw = av.value_bool
            else:
                raw = (
                    (av.value_text or {}).get("uz", "") if isinstance(av.value_text, dict) else av.value_text
                )
            out.append(
                {
                    "code": av.attribute.code,
                    "variant_id": av.variant_id,
                    "value": av.display("uz"),
                    "raw": raw,
                }
            )
        return out

    @transaction.atomic
    def _save_attributes(self, product, items):
        if items is None:
            return
        allowed = {a.code: a for a in Attribute.objects.filter(code__in=[i["code"] for i in items])}
        for item in items:
            attr = allowed.get(item["code"])
            if attr is None:
                raise serializers.ValidationError({"attributes": f"Noma'lum xususiyat: {item['code']}"})
            variant_id = item.get("variant_id")
            if variant_id and not product.variants.filter(pk=variant_id).exists():
                raise serializers.ValidationError(
                    {"attributes": f"Variant {variant_id} bu tovarga tegishli emas"}
                )
            lookup = {"product": product, "attribute": attr, "variant_id": variant_id}
            if item["value"] is None:
                AttributeValue.objects.filter(**lookup).delete()
                continue
            AttributeValue.objects.update_or_create(**lookup, defaults=_attr_kwargs(attr, item["value"]))

    def create(self, validated):
        from .importer import _unique_slug

        items = validated.pop("attributes", None)
        if not validated.get("slug"):
            validated["slug"] = _unique_slug(validated["name"].get("uz", ""))
        product = super().create(validated)
        self._save_attributes(product, items)
        return product

    def update(self, instance, validated):
        items = validated.pop("attributes", None)
        product = super().update(instance, validated)
        self._save_attributes(product, items)
        return product


class PriceChangeSerializer(serializers.Serializer):
    price = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    old_price = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)


class PriceHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceHistory
        fields = ["price", "old_price", "source", "changed_by", "created_at"]


class ImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImport
        fields = [
            "id",
            "file",
            "dry_run",
            "status",
            "rows_total",
            "rows_ok",
            "rows_failed",
            "errors",
            "created_at",
        ]
        read_only_fields = ["status", "rows_total", "rows_ok", "rows_failed", "errors", "created_at"]

    def validate_file(self, f):
        if not f.name.lower().endswith(".xlsx"):
            raise serializers.ValidationError("Faqat .xlsx fayl.")
        if f.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Fayl 10 MB dan katta.")
        return f


# --- viewsets ---
class _AdminViewSet(viewsets.ModelViewSet):
    permission_classes = [ContentManager]
    pagination_class = AdminPagination


@extend_schema(tags=["admin: catalog"])
class CategoryAdminViewSet(_AdminViewSet):
    serializer_class = CategoryAdminSerializer
    queryset = Category.objects.all().order_by("sort", "id")


@extend_schema(tags=["admin: catalog"])
class BrandAdminViewSet(_AdminViewSet):
    serializer_class = BrandAdminSerializer
    queryset = Brand.objects.all()
    parser_classes = [MultiPartParser, FormParser]


@extend_schema(tags=["admin: catalog"])
class AttributeAdminViewSet(_AdminViewSet):
    serializer_class = AttributeAdminSerializer
    queryset = Attribute.objects.prefetch_related("options")


@extend_schema(tags=["admin: catalog"])
class ProductAdminViewSet(_AdminViewSet):
    serializer_class = ProductAdminSerializer

    def get_queryset(self):
        qs = (
            Product.objects.select_related("category", "brand")
            .prefetch_related("variants", "images", "attribute_values__attribute", "attribute_values__option")
            .order_by("-id")
        )
        p = self.request.query_params
        if v := p.get("status"):
            qs = qs.filter(status=v)
        if v := p.get("category"):
            qs = qs.filter(category_id=v)
        if v := p.get("q"):
            qs = qs.filter(search_text__contains=v.lower())
        return qs

    def destroy(self, request, *args, **kwargs):
        # Tovarlar o'chirilmaydi (buyurtmalar tarixi) — arxivlanadi.
        product = self.get_object()
        product.status = Product.Status.ARCHIVED
        product.save(update_fields=["status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["admin: catalog"])
class VariantAdminViewSet(_AdminViewSet):
    serializer_class = VariantAdminSerializer

    def get_queryset(self):
        qs = ProductVariant.objects.select_related("product").order_by("product_id", "sort", "id")
        if v := self.request.query_params.get("product"):
            qs = qs.filter(product_id=v)
        if v := self.request.query_params.get("sku"):
            qs = qs.filter(sku__icontains=v)
        return qs

    def destroy(self, request, *args, **kwargs):
        variant = self.get_object()
        variant.is_active = False
        variant.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=PriceChangeSerializer, responses=VariantAdminSerializer)
    @action(detail=True, methods=["patch"])
    def price(self, request, pk=None):
        ser = PriceChangeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        variant = change_price(
            self.get_object(),
            ser.validated_data["price"],
            ser.validated_data.get("old_price"),
            source=PriceHistory.Source.MANUAL,
            user=request.user,
        )
        return Response(VariantAdminSerializer(variant, context={"request": request}).data)

    @extend_schema(responses=PriceHistorySerializer(many=True))
    @action(detail=True, methods=["get"], url_path="price-history")
    def price_history(self, request, pk=None):
        return Response(PriceHistorySerializer(self.get_object().price_history.all()[:100], many=True).data)


@extend_schema(tags=["admin: catalog"])
class ProductImageAdminViewSet(_AdminViewSet):
    serializer_class = ProductImageAdminSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        qs = ProductImage.objects.all()
        if v := self.request.query_params.get("product"):
            qs = qs.filter(product_id=v)
        return qs


@extend_schema(tags=["admin: catalog"])
class ImportAdminViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    permission_classes = [ContentManager]
    pagination_class = AdminPagination
    serializer_class = ImportSerializer
    parser_classes = [MultiPartParser, FormParser]
    queryset = ProductImport.objects.all()

    def perform_create(self, serializer):
        from .tasks import run_import_task

        job = serializer.save(created_by=self.request.user)
        transaction.on_commit(lambda: run_import_task.delay(job.pk))

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        job = ProductImport.objects.get(pk=response.data["id"])
        return Response(
            ImportSerializer(job, context={"request": request}).data, status=status.HTTP_202_ACCEPTED
        )

    @extend_schema(
        responses={(200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"): bytes}
    )
    @action(detail=False, methods=["get"], url_path="template.xlsx")
    def template(self, request):
        resp = HttpResponse(
            build_template(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        resp["Content-Disposition"] = 'attachment; filename="tovarlar-shablon.xlsx"'
        return resp
