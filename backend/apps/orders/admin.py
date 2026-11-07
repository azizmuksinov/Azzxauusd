from django.contrib import admin

from .models import Order, OrderItem, OrderStatusHistory


class ItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = [f.name for f in OrderItem._meta.fields]
    can_delete = False


class HistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = [f.name for f in OrderStatusHistory._meta.fields]
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["number", "user", "status", "payment_method", "payment_status", "total", "created_at"]
    list_filter = ["status", "payment_method", "payment_status", "delivery_provider"]
    search_fields = ["number", "user__phone", "recipient_phone"]
    # Status faqat statuslar mashinasi orqali o'zgaradi (admin API) — bu yerda faqat ko'rish.
    readonly_fields = [f.name for f in Order._meta.fields]
    inlines = [ItemInline, HistoryInline]

    def has_add_permission(self, request):
        return False
