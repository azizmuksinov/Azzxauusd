"""Mijozlar chati: avval AI yordamchi javob beradi, kerak bo'lsa suhbat xodimga o'tadi."""

import secrets

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


def new_token() -> str:
    return secrets.token_urlsafe(24)


class Conversation(TimeStampedModel):
    class Status(models.TextChoices):
        AI = "ai", "AI javob beryapti"
        WAITING = "waiting", "Xodim kutilmoqda"
        STAFF = "staff", "Xodim javob beryapti"
        CLOSED = "closed", "Yopilgan"

    # Mehmon ham yoza oladi: suhbat brauzerda saqlanadigan maxfiy token bilan ochiladi.
    token = models.CharField(max_length=48, unique=True, default=new_token)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="chats"
    )
    name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    lang = models.CharField(max_length=8, default="uz")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.AI)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    unread_for_staff = models.PositiveIntegerField(default=0)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-last_message_at", "-id"]
        verbose_name = "Suhbat"
        verbose_name_plural = "Suhbatlar"

    def __str__(self):
        return f"Suhbat #{self.pk} ({self.get_status_display()})"


class Message(models.Model):
    class Sender(models.TextChoices):
        CUSTOMER = "customer", "Mijoz"
        AI = "ai", "AI yordamchi"
        STAFF = "staff", "Xodim"
        SYSTEM = "system", "Tizim"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=8, choices=Sender.choices)
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    text = models.TextField()
    # AI tavsiya qilgan tovarlar: [{slug, name, price, image}]
    products = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Xabar"
        verbose_name_plural = "Xabarlar"

    def __str__(self):
        return f"{self.get_sender_display()}: {self.text[:40]}"
