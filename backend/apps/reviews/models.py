from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class Review(TimeStampedModel):
    """Sharh faqat tovarni olgan (buyurtmasi yetkazilgan) xaridordan; bitta xaridor — bitta sharh."""

    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField(blank=True, max_length=3000)
    pros = models.CharField(max_length=500, blank=True)
    cons = models.CharField(max_length=500, blank=True)
    is_published = models.BooleanField(default=True, help_text="Moderator yashirishi mumkin")
    reply = models.TextField(blank=True, help_text="Do'kon javobi")

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "sharh"
        verbose_name_plural = "sharhlar"
        constraints = [models.UniqueConstraint(fields=["product", "user"], name="uniq_review_per_user")]
        indexes = [models.Index(fields=["product", "is_published", "-created_at"])]

    def __str__(self):
        return f"{self.product_id}: {self.rating}★"
