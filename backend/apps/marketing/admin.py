from django.contrib import admin

from .models import Banner


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ["__str__", "link", "sort", "is_active", "starts_at", "ends_at"]
    list_editable = ["sort", "is_active"]
