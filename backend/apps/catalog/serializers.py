from rest_framework import serializers

from apps.core.i18n import localize, request_language

from .models import Brand, Category, Product, ProductImage
from .selectors import stock_status


class LangMixin:
    @property
    def lang(self) -> str:
        if "lang" not in self.context:
            self.context["lang"] = request_language(self.context.get("request"))
        return self.context["lang"]

    def tr(self, value) -> str:
        return localize(value, self.lang)


class BrandSerializer(LangMixin, serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = ["slug", "name", "logo"]

    def get_logo(self, obj) -> str:
        return obj.logo.url if obj.logo else ""


class CategoryShortSerializer(LangMixin, serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "slug", "name"]

    def get_name(self, obj) -> str:
        return self.tr(obj.name)


class CategoryDetailSerializer(CategoryShortSerializer):
    breadcrumbs = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta(CategoryShortSerializer.Meta):
        fields = ["id", "slug", "name", "icon", "breadcrumbs", "children"]

    def get_breadcrumbs(self, obj) -> list[dict]:
        return CategoryShortSerializer(obj.ancestors(), many=True, context=self.context).data

    def get_children(self, obj) -> list[dict]:
        kids = obj.children.filter(is_active=True)
        return CategoryShortSerializer(kids, many=True, context=self.context).data


def _main_image(product) -> str:
    images = getattr(product, "prefetched_images", None)
    if images is None:
        images = list(product.images.all()[:1])
    return images[0].url if images else ""


def _discount_percent(price, old_price) -> int:
    if not price or not old_price or old_price <= price:
        return 0
    return int(round((1 - price / old_price) * 100))


class ProductCardSerializer(LangMixin, serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()
    price = serializers.DecimalField(source="min_price", max_digits=14, decimal_places=2, read_only=True)
    old_price = serializers.DecimalField(
        source="min_old_price", max_digits=14, decimal_places=2, read_only=True
    )
    discount_percent = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    variant_id = serializers.IntegerField(
        source="default_variant_id", read_only=True, help_text="Eng arzon variant"
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "slug",
            "name",
            "category_slug",
            "variant_id",
            "brand",
            "price",
            "old_price",
            "discount_percent",
            "image",
            "rating_avg",
            "rating_count",
            "stock_status",
            "is_bulky",
        ]

    def get_name(self, obj) -> str:
        return self.tr(obj.name)

    def get_brand(self, obj) -> dict | None:
        return {"slug": obj.brand.slug, "name": obj.brand.name} if obj.brand_id else None

    def get_discount_percent(self, obj) -> int:
        return _discount_percent(obj.min_price, obj.min_old_price)

    def get_image(self, obj) -> str:
        return _main_image(obj)

    def get_stock_status(self, obj) -> str:
        return stock_status(obj.available)


class ImageSerializer(LangMixin, serializers.ModelSerializer):
    url = serializers.CharField(read_only=True)
    alt = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "url", "alt", "variant_id"]

    def get_alt(self, obj) -> str:
        return self.tr(obj.alt)


class ProductDetailSerializer(ProductCardSerializer):
    description = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    attributes = serializers.SerializerMethodField()

    class Meta(ProductCardSerializer.Meta):
        fields = ProductCardSerializer.Meta.fields + [
            "description",
            "model_code",
            "warranty_months",
            "category",
            "images",
            "variants",
            "attributes",
        ]

    def get_description(self, obj) -> str:
        return self.tr(obj.description)

    def get_category(self, obj) -> dict:
        return CategoryDetailSerializer(obj.category, context=self.context).data["breadcrumbs"]

    def get_images(self, obj) -> list[dict]:
        return ImageSerializer(obj.images.all(), many=True, context=self.context).data

    def get_variants(self, obj) -> list[dict]:
        from apps.inventory.services import available_by_variant

        variants = list(obj.variants.filter(is_active=True))
        avail = available_by_variant(v.id for v in variants)
        options: dict[int, dict] = {}
        for av in obj.attribute_values.filter(variant__isnull=False).select_related("attribute", "option"):
            options.setdefault(av.variant_id, {})[av.attribute.code] = {
                "name": self.tr(av.attribute.name),
                "value": av.display(self.lang),
                "option": av.option.code if av.option_id else None,
            }
        return [
            {
                "id": v.id,
                "sku": v.sku,
                "name_suffix": self.tr(v.name_suffix),
                "price": str(v.price),
                "old_price": str(v.old_price) if v.old_price else None,
                "discount_percent": _discount_percent(v.price, v.old_price),
                "stock_status": stock_status(avail.get(v.id, 0)),
                "options": options.get(v.id, {}),
            }
            for v in variants
        ]

    def get_attributes(self, obj) -> list[dict]:
        groups: dict[str, list] = {}
        values = (
            obj.attribute_values.filter(variant__isnull=True)
            .select_related("attribute", "option")
            .order_by("attribute__sort", "attribute__id")
        )
        for av in values:
            group = self.tr(av.attribute.group_name) or ""
            groups.setdefault(group, []).append(
                {
                    "code": av.attribute.code,
                    "name": self.tr(av.attribute.name),
                    "value": av.display(self.lang),
                }
            )
        return [{"group": g, "items": items} for g, items in groups.items()]
