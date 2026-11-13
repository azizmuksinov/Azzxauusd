from django.contrib import admin

from .models import DeliveryQuote, DeliveryTariff, DeliveryZone


class TariffInline(admin.TabularInline):
    model = DeliveryTariff
    extra = 0


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ["name", "eta_days_min", "eta_days_max", "is_active", "sort"]
    filter_horizontal = ["regions", "districts"]
    inlines = [TariffInline]


@admin.register(DeliveryQuote)
class DeliveryQuoteAdmin(admin.ModelAdmin):
    list_display = [
        "public_id",
        "user",
        "provider",
        "delivery_price",
        "lifting_price",
        "expires_at",
        "used_at",
    ]
    readonly_fields = [f.name for f in DeliveryQuote._meta.fields]
