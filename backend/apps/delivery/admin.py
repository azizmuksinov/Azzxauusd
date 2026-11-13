from django.contrib import admin

from .models import CashHandover, CodCollection, Courier, DeliveryAttempt, HandoverAct, RouteSheet, RouteStop


@admin.register(Courier)
class CourierAdmin(admin.ModelAdmin):
    list_display = ["__str__", "user", "vehicle", "warehouse", "is_active"]
    list_filter = ["vehicle", "is_active"]
    raw_id_fields = ["user"]


class RouteStopInline(admin.TabularInline):
    model = RouteStop
    extra = 0
    fields = ["sequence", "order", "result", "started_at", "finished_at"]
    readonly_fields = ["order", "result", "started_at", "finished_at"]
    can_delete = False


@admin.register(RouteSheet)
class RouteSheetAdmin(admin.ModelAdmin):
    """Marshrutni yaratish/berish/yopish — /xodim sahifasi yoki API orqali (holat o'tishlari tekshiriladi)."""

    list_display = ["number", "date", "courier", "warehouse", "status"]
    list_filter = ["status", "date", "courier"]
    readonly_fields = ["number", "status", "issued_at", "issued_by", "closed_at", "closed_by", "created_by"]
    inlines = [RouteStopInline]

    def has_add_permission(self, request):
        return False


@admin.register(DeliveryAttempt)
class DeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ["order", "outcome", "courier", "created_at"]
    list_filter = ["outcome"]
    search_fields = ["order__number"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(HandoverAct)
class HandoverActAdmin(DeliveryAttemptAdmin):
    list_display = ["number", "order", "courier", "door_payment", "amount_collected", "created_at"]
    list_filter = ["door_payment"]


@admin.register(CodCollection)
class CodCollectionAdmin(DeliveryAttemptAdmin):
    list_display = ["order", "courier", "amount", "handover", "created_at"]
    list_filter = ["courier"]


@admin.register(CashHandover)
class CashHandoverAdmin(DeliveryAttemptAdmin):
    list_display = ["number", "courier", "account", "amount", "accepted_by", "created_at"]
    list_filter = ["courier"]
    search_fields = ["number"]
