from django.contrib import admin

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


class CategoryAttributeInline(admin.TabularInline):
    model = CategoryAttribute
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["__str__", "slug", "parent", "sort", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["slug"]
    inlines = [CategoryAttributeInline]


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active"]
    search_fields = ["name", "slug"]


class AttributeOptionInline(admin.TabularInline):
    model = AttributeOption
    extra = 0


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ["code", "data_type", "unit", "is_filterable", "is_comparable"]
    inlines = [AttributeOptionInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ["sku", "product", "price", "cost_price", "is_active"]
    search_fields = ["sku", "barcode", "product__search_text"]  # back-office qatorlarida autocomplete uchun
    list_select_related = ["product"]


class VariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ["sku", "price", "old_price", "cost_price", "is_active"]


class ImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class AttributeValueInline(admin.TabularInline):
    model = AttributeValue
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["__str__", "category", "brand", "status", "is_bulky", "updated_at"]
    list_filter = ["status", "category", "brand", "is_bulky"]
    search_fields = ["search_text", "slug"]
    inlines = [VariantInline, AttributeValueInline, ImageInline]


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ["variant", "price", "old_price", "source", "changed_by", "created_at"]
    list_filter = ["source"]
    search_fields = ["variant__sku"]


@admin.register(ProductImport)
class ProductImportAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "status",
        "dry_run",
        "rows_total",
        "rows_ok",
        "rows_failed",
        "created_by",
        "created_at",
    ]
