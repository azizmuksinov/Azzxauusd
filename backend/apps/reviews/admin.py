from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["product", "user", "rating", "is_published", "created_at"]
    list_filter = ["rating", "is_published"]
    search_fields = ["product__slug", "text"]
