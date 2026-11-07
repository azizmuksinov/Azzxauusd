from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import TimeStampedModel


class Warehouse(TimeStampedModel):
    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=128)
    district = models.ForeignKey(
        "geo.District", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    address = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # Saytda sotuv uchun hisoblanadimi (masalan, brak ombori — yo'q).
    is_sellable = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name


class Stock(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stocks")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT, related_name="stocks")
    on_hand = models.IntegerField(default=0)
    reserved = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["warehouse", "variant"], name="uniq_stock"),
            models.CheckConstraint(condition=Q(on_hand__gte=0), name="stock_on_hand_gte_0"),
            models.CheckConstraint(condition=Q(reserved__gte=0), name="stock_reserved_gte_0"),
            models.CheckConstraint(
                condition=Q(reserved__lte=F("on_hand")), name="stock_reserved_lte_on_hand"
            ),
        ]

    def __str__(self):
        return f"{self.variant_id}@{self.warehouse_id}: {self.on_hand}/{self.reserved}"

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


class StockMovement(models.Model):
    class Reason(models.TextChoices):
        RECEIPT = "receipt", "Kirim"
        SALE = "sale", "Sotuv"
        RETURN = "return", "Qaytarish"
        TRANSFER_OUT = "transfer_out", "Ko'chirish (chiqim)"
        TRANSFER_IN = "transfer_in", "Ko'chirish (kirim)"
        ADJUSTMENT = "adjustment", "Tuzatish"
        WRITE_OFF = "write_off", "Hisobdan chiqarish"

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="+")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT, related_name="+")
    delta = models.IntegerField()
    on_hand_after = models.IntegerField()
    reason = models.CharField(max_length=12, choices=Reason.choices)
    ref_type = models.CharField(max_length=32, blank=True)
    ref_id = models.CharField(max_length=64, blank=True)
    comment = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["variant", "-created_at"]),
            models.Index(fields=["ref_type", "ref_id"]),
        ]

    def __str__(self):
        return f"{self.reason} {self.delta:+d}"


class Reservation(TimeStampedModel):
    """Buyurtma uchun qoldiq band qilinishi. orders moduli paydo bo'lgach ref = ("order", id)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Faol"
        COMMITTED = "committed", "Sotildi"
        RELEASED = "released", "Bo'shatildi"

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="+")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT, related_name="+")
    qty = models.PositiveIntegerField()
    ref_type = models.CharField(max_length=32)
    ref_id = models.CharField(max_length=64)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["ref_type", "ref_id"]), models.Index(fields=["status", "expires_at"])]

    def __str__(self):
        return f"{self.ref_type}:{self.ref_id} x{self.qty}"


class SerialUnit(TimeStampedModel):
    class Status(models.TextChoices):
        IN_STOCK = "in_stock", "Omborda"
        RESERVED = "reserved", "Band"
        SOLD = "sold", "Sotilgan"
        RETURNED = "returned", "Qaytarilgan"
        DEFECTIVE = "defective", "Nuqsonli"
        WRITTEN_OFF = "written_off", "Hisobdan chiqarilgan"

    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.PROTECT, related_name="serial_units"
    )
    warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    serial_number = models.CharField(max_length=64, blank=True)
    imei1 = models.CharField(max_length=15, null=True, blank=True, unique=True)
    imei2 = models.CharField(max_length=15, null=True, blank=True, unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_STOCK)
    received_at = models.DateTimeField(auto_now_add=True)
    history = models.JSONField(default=list, blank=True, help_text="[{at, status, ref, by}]")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "serial_number"],
                condition=~Q(serial_number=""),
                name="uniq_variant_serial",
            ),
            models.CheckConstraint(
                condition=~Q(serial_number="") | Q(imei1__isnull=False), name="serial_or_imei_required"
            ),
        ]
        indexes = [models.Index(fields=["status"]), models.Index(fields=["serial_number"])]

    def __str__(self):
        return self.serial_number or self.imei1 or str(self.pk)
