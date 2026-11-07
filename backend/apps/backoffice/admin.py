"""Django admin: back-office hujjatlari. Demo'da sinab ko'rish uchun asosiy interfeys."""

from django.contrib import admin, messages

from apps.core.exceptions import ApiError

from . import services
from .models import (
    CashAccount,
    CashTransaction,
    DocStatus,
    PurchaseReceipt,
    PurchaseReceiptLine,
    StockTransfer,
    StockTransferLine,
    Supplier,
    WriteOff,
    WriteOffLine,
)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["name", "inn", "phone", "debt", "is_active"]
    search_fields = ["name", "inn", "phone"]
    list_filter = ["is_active"]

    @admin.display(description="Qarzimiz, so'm")
    def debt(self, obj):
        return services.supplier_balance(obj)["debt"]


class _DocAdmin(admin.ModelAdmin):
    post_fn = None
    actions = ["post_selected", "cancel_selected"]
    list_filter = ["status"]
    readonly_fields = ["number", "status", "created_by", "posted_at", "posted_by"]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status != DocStatus.DRAFT:
            return [f.name for f in self.model._meta.fields]
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Tanlanganlarni o'tkazish (qoldiqqa ta'sir qiladi)")
    def post_selected(self, request, queryset):
        for doc in queryset:
            try:
                type(self).post_fn(doc, request.user)
                self.message_user(request, f"{doc}: o'tkazildi", messages.SUCCESS)
            except ApiError as exc:
                self.message_user(request, f"{doc}: {exc.detail}", messages.ERROR)

    @admin.action(description="Tanlangan qoralamalarni bekor qilish")
    def cancel_selected(self, request, queryset):
        for doc in queryset:
            try:
                services.cancel_draft(self.model, doc)
                self.message_user(request, f"{doc}: bekor qilindi", messages.SUCCESS)
            except ApiError as exc:
                self.message_user(request, f"{doc}: {exc.detail}", messages.ERROR)


class _LineInline(admin.TabularInline):
    extra = 1
    autocomplete_fields = ["variant"]

    def has_change_permission(self, request, obj=None):
        return obj is None or obj.status == DocStatus.DRAFT

    has_add_permission = has_delete_permission = has_change_permission


class ReceiptLineInline(_LineInline):
    model = PurchaseReceiptLine


@admin.register(PurchaseReceipt)
class PurchaseReceiptAdmin(_DocAdmin):
    post_fn = staticmethod(services.post_receipt)
    list_display = ["number", "supplier", "warehouse", "supplier_doc_number", "total", "status", "created_at"]
    search_fields = ["number", "supplier__name", "supplier_doc_number"]
    fields = [
        "supplier",
        "warehouse",
        "supplier_doc_number",
        "supplier_doc_date",
        "comment",
        "number",
        "status",
        "created_by",
        "posted_at",
        "posted_by",
    ]
    inlines = [ReceiptLineInline]

    @admin.display(description="Jami, so'm")
    def total(self, obj):
        return obj.total


class TransferLineInline(_LineInline):
    model = StockTransferLine


@admin.register(StockTransfer)
class StockTransferAdmin(_DocAdmin):
    post_fn = staticmethod(services.post_transfer)
    list_display = ["number", "source", "target", "status", "created_at"]
    inlines = [TransferLineInline]


class WriteOffLineInline(_LineInline):
    model = WriteOffLine


@admin.register(WriteOff)
class WriteOffAdmin(_DocAdmin):
    post_fn = staticmethod(services.post_write_off)
    list_display = ["number", "warehouse", "reason", "status", "created_at"]
    list_filter = ["status", "reason"]
    inlines = [WriteOffLineInline]


@admin.register(CashAccount)
class CashAccountAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "balance", "is_active"]

    @admin.display(description="Qoldiq, so'm")
    def balance(self, obj):
        return services.balance(obj)


@admin.register(CashTransaction)
class CashTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "occurred_at",
        "account",
        "direction",
        "amount",
        "category",
        "supplier",
        "order",
        "comment",
    ]
    list_filter = ["account", "direction", "category"]
    search_fields = ["comment", "supplier__name", "order__number"]
    autocomplete_fields = ["supplier"]
    raw_id_fields = ["order"]
    actions = ["reverse_selected"]
    fields = ["account", "direction", "amount", "category", "supplier", "order", "comment", "occurred_at"]

    def get_readonly_fields(self, request, obj=None):
        return self.fields if obj else []  # yozuvlar o'zgartirilmaydi

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change:
            return
        try:
            services.record_cash(
                account=obj.account,
                direction=obj.direction,
                amount=obj.amount,
                category=obj.category,
                supplier=obj.supplier,
                order=obj.order,
                comment=obj.comment,
                occurred_at=obj.occurred_at,
                user=request.user,
            )
        except ApiError as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)

    @admin.action(description="Teskari yozuv bilan bekor qilish")
    def reverse_selected(self, request, queryset):
        for tx in queryset:
            try:
                services.reverse_cash(tx, request.user, f"Admin: #{tx.pk} bekor qilindi")
                self.message_user(request, f"#{tx.pk}: bekor qilindi", messages.SUCCESS)
            except ApiError as exc:
                self.message_user(request, f"#{tx.pk}: {exc.detail}", messages.ERROR)
