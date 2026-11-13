import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class DeliveryZone(TimeStampedModel):
    """Yetkazish hududi: viloyatlar va/yoki tumanlar to'plami. Tuman bo'yicha moslik viloyatdan ustun."""

    name = models.CharField(max_length=128)
    regions = models.ManyToManyField("geo.Region", blank=True, related_name="delivery_zones")
    districts = models.ManyToManyField("geo.District", blank=True, related_name="delivery_zones")
    eta_days_min = models.PositiveSmallIntegerField(default=1)
    eta_days_max = models.PositiveSmallIntegerField(default=3)
    is_active = models.BooleanField(default=True)
    sort = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort", "id"]

    def __str__(self):
        return self.name


class DeliveryTariff(models.Model):
    """Zona + transport turi + vazn chegarasi bo'yicha narx.

    Mos keladigan eng kichik `max_weight_kg` tanlanadi.
    """

    class Vehicle(models.TextChoices):
        STANDARD = "standard", "Oddiy (yengil)"
        TRUCK = "truck", "Yuk mashinasi (yirik texnika)"

    zone = models.ForeignKey(DeliveryZone, on_delete=models.CASCADE, related_name="tariffs")
    vehicle = models.CharField(max_length=10, choices=Vehicle.choices, default=Vehicle.STANDARD)
    max_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, help_text="Bo'sh — cheklovsiz"
    )
    price = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["zone", "vehicle", models.F("max_weight_kg").asc(nulls_last=True)]
        constraints = [
            models.UniqueConstraint(fields=["zone", "vehicle", "max_weight_kg"], name="uniq_tariff"),
            models.CheckConstraint(condition=Q(price__gte=0), name="tariff_price_gte_0"),
        ]

    def __str__(self):
        return f"{self.zone} / {self.vehicle} / ≤{self.max_weight_kg or '∞'} kg: {self.price}"


class DeliveryQuote(models.Model):
    """Checkout'da hisoblangan yetkazish narxi. Buyurtmada shu narx ishlatiladi (narx "qotadi")."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    address = models.ForeignKey("accounts.Address", on_delete=models.CASCADE, related_name="+")
    provider = models.CharField(max_length=16)
    cart_fingerprint = models.CharField(max_length=64)
    address_fingerprint = models.CharField(max_length=64)
    weight_kg = models.DecimalField(max_digits=10, decimal_places=3)
    bulky_items = models.PositiveIntegerField(default=0)
    vehicle = models.CharField(max_length=10)
    delivery_price = models.DecimalField(max_digits=14, decimal_places=2)
    lifting_available = models.BooleanField(default=False)
    lifting_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    eta_days_min = models.PositiveSmallIntegerField()
    eta_days_max = models.PositiveSmallIntegerField()
    raw = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.provider} {self.delivery_price}"


class PickupPoint(TimeStampedModel):
    """Olib ketish punkti (do'kon yoki ombor): xaridor buyurtmani o'zi kelib oladi — yetkazish bepul."""

    name = models.CharField(max_length=120)
    address = models.CharField(max_length=255)
    landmark = models.CharField("mo'ljal", max_length=255, blank=True)
    hours = models.CharField("ish vaqti", max_length=120, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sort = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort", "id"]
        verbose_name = "olib ketish punkti"
        verbose_name_plural = "olib ketish punktlari"

    def __str__(self):
        return self.name
