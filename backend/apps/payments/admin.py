from django.contrib import admin

from .models import Payment, WebhookLog


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["created_at", "order", "provider", "provider_txn_id", "amount", "status", "performed_at"]
    list_filter = ["provider", "status"]
    search_fields = ["provider_txn_id", "order__number"]
    readonly_fields = [f.name for f in Payment._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "provider", "path", "ip", "signature_valid"]
    list_filter = ["provider", "signature_valid"]
    readonly_fields = [f.name for f in WebhookLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
