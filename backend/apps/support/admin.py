from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ["sender", "text", "created_at"]
    readonly_fields = fields


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "status", "name", "phone", "user", "last_message_at", "unread_for_staff"]
    list_filter = ["status"]
    exclude = ["token"]
    inlines = [MessageInline]
