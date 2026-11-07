from django.db import models

from apps.core.models import TimeStampedModel


class Provider(models.TextChoices):
    PAYME = "payme", "Payme"
    CLICK = "click", "Click"
    UZUM = "uzum", "Uzum Bank"
    DEMO = "demo", "Demo (faqat DEMO_MODE)"


class Payment(TimeStampedModel):
    """Bitta provayder tranzaksiyasi.

    Summa — so'mda (Payme/Uzum tiyin bilan ishlaydi, chegarada o'giriladi).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"  # yaratildi, hali yechilmadi (Payme state=1, Click prepare)
        SUCCEEDED = "succeeded", "To'landi"
        CANCELLED = "cancelled", "Bekor qilindi"  # yechilmasdan bekor
        REFUNDED = "refunded", "Qaytarildi"  # yechilgandan keyin bekor

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=8, choices=Provider.choices)
    provider_txn_id = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # Payme: provayder vaqtlari (ms) va holati
    provider_time = models.BigIntegerField(null=True, blank=True, help_text="Provayder yaratgan vaqt (ms)")
    performed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.IntegerField(null=True, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "provider_txn_id"], name="uniq_provider_txn")
        ]
        indexes = [models.Index(fields=["order", "status"])]

    def __str__(self):
        return f"{self.provider}:{self.provider_txn_id} {self.amount} {self.status}"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.PENDING


class WebhookLog(models.Model):
    """Har bir kiruvchi webhook xom holda yoziladi (imzo tekshiruvidan oldin) — nizolar va audit uchun."""

    provider = models.CharField(max_length=8, choices=Provider.choices)
    path = models.CharField(max_length=128)
    ip = models.GenericIPAddressField(null=True, blank=True)
    body = models.JSONField(null=True, blank=True)
    signature_valid = models.BooleanField(null=True)
    response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["provider", "-created_at"])]

    def __str__(self):
        return f"{self.provider} {self.path} {self.created_at:%Y-%m-%d %H:%M}"
