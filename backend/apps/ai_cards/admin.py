from django.contrib import admin

from .models import CardBatch, CardDraft


class DraftInline(admin.TabularInline):
    model = CardDraft
    extra = 0
    fields = ["row_number", "query", "status", "product"]
    readonly_fields = fields
    can_delete = False


@admin.register(CardBatch)
class CardBatchAdmin(admin.ModelAdmin):
    list_display = ["file_name", "rows_total", "created_by", "created_at"]
    inlines = [DraftInline]


@admin.register(CardDraft)
class CardDraftAdmin(admin.ModelAdmin):
    """Ko'rib chiqish va nashr qilish — /xodim → "AI kartochkalar"."""

    list_display = ["query", "batch", "status", "product", "updated_at"]
    list_filter = ["status"]
    search_fields = ["query", "supplier_sku"]
    readonly_fields = ["batch", "raw", "result", "warnings", "error", "model_used", "product", "reviewed_by"]
