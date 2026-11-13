from django.contrib import admin

from .models import District, Region


class DistrictInline(admin.TabularInline):
    model = District
    extra = 0


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "soato_code", "sort"]
    inlines = [DistrictInline]


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ["__str__", "region", "bts_city_code", "fargo_city_code", "is_active"]
    list_filter = ["region", "is_active"]
