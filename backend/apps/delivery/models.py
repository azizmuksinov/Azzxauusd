"""Ombordan eshikkacha: yig'ish (seriya raqamlar), kuryerlar, marshrut varaqlari, urinishlar,
topshirish akti va kuryer naqd puli.

Asosiy qoidalar (docs/01-arxitektura.md, 11-bo'lim):
- Buyurtmani kuryerga logist biriktiradi (marshrut varag'i).
- Mijoz topilmasa — urinish yoziladi; `delivery_max_attempts` (3) ta urinishdan keyin tovar omborga qaytadi.
- Eshikda to'lov: naqd yoki Payme/Click QR. Naqd pulni kuryer kun oxirida kassirga topshiradi.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel
from apps.logistics.models import DeliveryTariff


class _Numbered(TimeStampedModel):
    PREFIX = ""
    number = models.CharField(max_length=20, unique=True, null=True, editable=False)  # noqa: DJ001

    class Meta:
        abstract = True

    def __str__(self):
        return self.number or f"{self.PREFIX}-?"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"{self.PREFIX}-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(number=self.number)


class OrderItemSerial(models.Model):
    """Yig'ishda buyurtma pozitsiyasiga biriktirilgan seriyali dona (IMEI / seriya raqam)."""

    order_item = models.ForeignKey("orders.OrderItem", on_delete=models.CASCADE, related_name="serials")
    serial_unit = models.ForeignKey("inventory.SerialUnit", on_delete=models.PROTECT, related_name="+")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "buyurtmadagi seriya raqam"
        verbose_name_plural = "buyurtmadagi seriya raqamlar"
        constraints = [
            models.UniqueConstraint(fields=["order_item", "serial_unit"], name="uniq_order_item_serial")
        ]

    def __str__(self):
        return f"{self.order_item_id}: {self.serial_unit}"


Vehicle = DeliveryTariff.Vehicle


class Courier(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="courier_profile"
    )
    vehicle = models.CharField(max_length=10, choices=Vehicle.choices, default=Vehicle.STANDARD)
    warehouse = models.ForeignKey(
        "inventory.Warehouse",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Asosiy ombori",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["user__first_name", "id"]
        verbose_name = "kuryer"
        verbose_name_plural = "kuryerlar"

    def __str__(self):
        name = f"{self.user.first_name} {self.user.last_name}".strip()
        return name or self.user.phone


class RouteSheet(_Numbered):
    """Marshrut varag'i: bir kuryerning bir kunlik buyurtmalari."""

    PREFIX = "MV"

    class Status(models.TextChoices):
        DRAFT = "draft", "Qoralama"
        ISSUED = "issued", "Kuryerga berildi"
        CLOSED = "closed", "Yopildi"

    courier = models.ForeignKey(Courier, on_delete=models.PROTECT, related_name="routes")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="+")
    date = models.DateField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    comment = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "marshrut varag'i"
        verbose_name_plural = "marshrut varaqlari"
        indexes = [models.Index(fields=["courier", "status"])]


class StopResult(models.TextChoices):
    PENDING = "pending", "Kutilmoqda"
    DELIVERED = "delivered", "Yetkazildi"
    REFUSED = "refused", "Rad etildi"
    FAILED = "failed", "Yetkazilmadi (mijoz topilmadi)"
    NOT_VISITED = "not_visited", "Borilmadi"


class RouteStop(models.Model):
    route = models.ForeignKey(RouteSheet, on_delete=models.CASCADE, related_name="stops")
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="route_stops")
    sequence = models.PositiveSmallIntegerField(default=0)
    result = models.CharField(max_length=12, choices=StopResult.choices, default=StopResult.PENDING)
    # Marshrut yopilguncha True: bitta buyurtma bir vaqtda faqat bitta ochiq marshrutda bo'ladi.
    is_open = models.BooleanField(default=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sequence", "id"]
        verbose_name = "marshrut nuqtasi"
        verbose_name_plural = "marshrut nuqtalari"
        constraints = [
            models.UniqueConstraint(fields=["route", "order"], name="uniq_route_order"),
            models.UniqueConstraint(
                fields=["order"], condition=Q(is_open=True), name="uniq_open_stop_per_order"
            ),
        ]

    def __str__(self):
        return f"{self.route} #{self.sequence}: {self.order}"


class DeliveryAttempt(models.Model):
    """Har bir eshikka borish natijasi.

    Muvaffaqiyatsiz urinishlar soni `delivery_max_attempts` bilan solishtiriladi.
    """

    class Outcome(models.TextChoices):
        DELIVERED = "delivered", "Yetkazildi"
        REFUSED = "refused", "Eshik oldida rad etdi"
        NOT_HOME = "not_home", "Mijoz uyda yo'q"
        NO_ANSWER = "no_answer", "Telefonni ko'tarmadi"
        WRONG_ADDRESS = "wrong_address", "Manzil noto'g'ri"
        RESCHEDULED = "rescheduled", "Mijoz boshqa vaqtni so'radi"

        @classmethod
        def failures(cls) -> set[str]:
            return {cls.NOT_HOME, cls.NO_ANSWER, cls.WRONG_ADDRESS, cls.RESCHEDULED}

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="delivery_attempts")
    stop = models.ForeignKey(RouteStop, on_delete=models.PROTECT, related_name="attempts")
    courier = models.ForeignKey(Courier, on_delete=models.PROTECT, related_name="+")
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    comment = models.CharField(max_length=500, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "yetkazish urinishi"
        verbose_name_plural = "yetkazish urinishlari"
        indexes = [models.Index(fields=["order", "outcome"])]

    def __str__(self):
        return f"{self.order} — {self.outcome}"


class DoorPayment(models.TextChoices):
    PREPAID = "prepaid", "Oldindan to'langan"
    CASH = "cash", "Naqd"
    QR = "qr", "Payme/Click QR"


class HandoverAct(_Numbered):
    """Topshirish akti: mijoz eshik oldida tovarni ko'rib, qabul qildi."""

    PREFIX = "TA"

    order = models.OneToOneField("orders.Order", on_delete=models.PROTECT, related_name="handover_act")
    stop = models.ForeignKey(RouteStop, on_delete=models.PROTECT, related_name="+")
    courier = models.ForeignKey(Courier, on_delete=models.PROTECT, related_name="+")
    inspection = models.JSONField(
        default=dict, help_text="{packaging_intact, appearance_ok, complete_set, powered_on}"
    )
    serials = models.JSONField(default=list, blank=True, help_text="Topshirilgan seriya raqamlar/IMEI")
    door_payment = models.CharField(max_length=8, choices=DoorPayment.choices)
    amount_collected = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    received_by = models.CharField(max_length=128, help_text="Qabul qilgan shaxs")
    comment = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "topshirish akti"
        verbose_name_plural = "topshirish aktlari"


class CashHandover(_Numbered):
    """Kuryer naqd pulni kassirga topshirdi (kun oxirida). Kassa hisobiga kirim yoziladi."""

    PREFIX = "KN"

    courier = models.ForeignKey(Courier, on_delete=models.PROTECT, related_name="handovers")
    account = models.ForeignKey("backoffice.CashAccount", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    cash_transaction = models.OneToOneField(
        "backoffice.CashTransaction", null=True, on_delete=models.PROTECT, related_name="+"
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    comment = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "kuryer naqd topshirishi"
        verbose_name_plural = "kuryer naqd topshirishlari"


class CodCollection(models.Model):
    """Kuryer eshik oldida olgan naqd pul.

    `handover` bo'sh bo'lsa — hali kassaga topshirilmagan (kuryer qarzi).
    """

    courier = models.ForeignKey(Courier, on_delete=models.PROTECT, related_name="collections")
    order = models.OneToOneField("orders.Order", on_delete=models.PROTECT, related_name="cod_collection")
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    handover = models.ForeignKey(
        CashHandover, null=True, blank=True, on_delete=models.PROTECT, related_name="collections"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "kuryer olgan naqd"
        verbose_name_plural = "kuryer olgan naqd pullar"
        indexes = [models.Index(fields=["courier", "handover"])]

    def __str__(self):
        return f"{self.order}: {self.amount}"
