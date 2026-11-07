from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class NotificationLog(TimeStampedModel):
    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        PUSH = "push", "Push"

    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        SENT = "sent", "Yuborildi"
        FAILED = "failed", "Xato"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    phone = models.CharField(max_length=16, blank=True)
    template_code = models.CharField(max_length=64)
    # OTP kodi bazaga yozilmaydi: OTP uchun body "***" bilan saqlanadi.
    body = models.TextField(blank=True)
    provider = models.CharField(max_length=32, blank=True)
    provider_message_id = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    error = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["phone", "-created_at"])]
