from django.contrib import admin

from .models import Setting


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ["key", "value", "updated_by", "updated_at"]
    readonly_fields = ["updated_by", "updated_at"]
