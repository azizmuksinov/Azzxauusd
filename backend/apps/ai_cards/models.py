"""Ta'minotchi Excel faylidan Gemini yordamida tovar kartochkalari (qoralama → xodim tekshiruvi → nashr)."""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class CardBatch(TimeStampedModel):
    """Yuklangan bitta Excel fayl."""

    file_name = models.CharField(max_length=255)
    columns = models.JSONField(default=dict, help_text="Aniqlangan ustunlar: {name, sku, price, qty, brand}")
    rows_total = models.PositiveIntegerField(default=0)
    currency = models.CharField(
        max_length=3, blank=True, help_text="Fayldagi narx valyutasi: UZS, USD yoki bo'sh (aniqlanmadi)"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "AI yuklama"
        verbose_name_plural = "AI yuklamalar"

    def __str__(self):
        return f"{self.file_name} ({self.rows_total})"


class CardDraft(TimeStampedModel):
    """Bitta qator: Gemini natijasi (qoralama). Tasdiqlansa — katalogda tovar yaratiladi."""

    class Status(models.TextChoices):
        PENDING = "pending", "Navbatda"
        READY = "ready", "Tekshirish kutilmoqda"
        NOT_FOUND = "not_found", "Topilmadi"
        FAILED = "failed", "Xato"
        APPROVED = "approved", "Nashr qilindi"
        REJECTED = "rejected", "Rad etildi"

    batch = models.ForeignKey(CardBatch, on_delete=models.CASCADE, related_name="drafts")
    row_number = models.PositiveIntegerField()
    query = models.CharField(max_length=500, help_text="Qidiriladigan nom (fayldan)")
    supplier_sku = models.CharField(max_length=64, blank=True)
    purchase_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    qty = models.IntegerField(null=True, blank=True)
    raw = models.JSONField(default=dict, help_text="Fayldagi qator")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    result = models.JSONField(default=dict, blank=True, help_text="Normallashtirilgan kartochka")
    warnings = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    model_used = models.CharField(max_length=64, blank=True)
    product = models.ForeignKey(
        "catalog.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["batch", "row_number"]
        verbose_name = "AI kartochka"
        verbose_name_plural = "AI kartochkalar"
        indexes = [models.Index(fields=["batch", "status"])]

    def __str__(self):
        return f"#{self.row_number} {self.query}"
