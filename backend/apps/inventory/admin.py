from django.contrib import admin

from .models import Reservation, SerialUnit, Stock, StockMovement, Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "district", "is_active", "is_sellable"]


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ["variant", "warehouse", "on_hand", "reserved", "updated_at"]
    list_filter = ["warehouse"]
    search_fields = ["variant__sku"]
    readonly_fields = ["on_hand", "reserved"]  # faqat servislar orqali o'zgaradi


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = [
        "created_at",
        "variant",
        "warehouse",
        "delta",
        "on_hand_after",
        "reason",
        "ref_type",
        "ref_id",
    ]
    list_filter = ["reason", "warehouse"]
    search_fields = ["variant__sku", "ref_id"]

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ["ref_type", "ref_id", "variant", "warehouse", "qty", "status", "expires_at"]
    list_filter = ["status"]


@admin.register(SerialUnit)
class SerialUnitAdmin(admin.ModelAdmin):
    list_display = ["__str__", "variant", "warehouse", "status", "received_at"]
    list_filter = ["status", "warehouse"]
    search_fields = ["serial_number", "imei1", "imei2"]
