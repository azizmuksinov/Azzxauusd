from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "channel", "phone", "template_code", "provider", "status"]
    list_filter = ["channel", "status", "provider", "template_code"]
    search_fields = ["phone", "provider_message_id"]
    readonly_fields = [f.name for f in NotificationLog._meta.fields]
