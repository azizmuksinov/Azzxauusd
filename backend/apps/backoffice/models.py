"""1C o'rniga: ta'minotchilar, ombor hujjatlari (kirim, ko'chirish, hisobdan chiqarish) va kassa.

Hujjat qoidasi: `draft` holatida tahrirlanadi; `post` qilinganda ombor qoldig'i o'zgaradi
va hujjat qulflanadi. O'tkazilgan hujjatni o'zgartirib bo'lmaydi — xato bo'lsa, teskari hujjat
(hisobdan chiqarish yoki ko'chirish) qilinadi.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class DocStatus(models.TextChoices):
    DRAFT = "draft", "Qoralama"
    POSTED = "posted", "O'tkazilgan"
    CANCELLED = "cancelled", "Bekor qilingan"


class Supplier(TimeStampedModel):
    name = models.CharField(max_length=200)
    inn = models.CharField("STIR (INN)", max_length=9, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    contact_person = models.CharField(max_length=128, blank=True)
    address = models.CharField(max_length=255, blank=True)
    bank_details = models.TextField(blank=True, help_text="Hisob raqami, bank, MFO")
    note = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["inn"], condition=~Q(inn=""), name="uniq_supplier_inn")
        ]

    def __str__(self):
        return self.name


class _Document(TimeStampedModel):
    PREFIX = ""
    number = models.CharField(max_length=20, unique=True, null=True, editable=False)  # noqa: DJ001
    status = models.CharField(max_length=10, choices=DocStatus.choices, default=DocStatus.DRAFT)
    comment = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        abstract = True
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.number or f"{self.PREFIX}-?"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"{self.PREFIX}-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(number=self.number)

    @property
    def is_draft(self) -> bool:
        return self.status == DocStatus.DRAFT


class PurchaseReceipt(_Document):
    """Ta'minotchidan kirim (xarid).

    O'tkazilganda qoldiq oshadi va tovar tannarxi o'rtacha og'irlikli qiymat bo'yicha yangilanadi.
    """

    PREFIX = "KR"
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="receipts")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="+")
    supplier_doc_number = models.CharField("Yuk xati / hisob-faktura raqami", max_length=64, blank=True)
    supplier_doc_date = models.DateField(null=True, blank=True)

    class Meta(_Document.Meta):
        verbose_name = "kirim hujjati"
        verbose_name_plural = "kirim hujjatlari"

    @property
    def total(self):
        return sum((line.qty * line.unit_cost for line in self.lines.all()), 0)


class PurchaseReceiptLine(models.Model):
    receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT, related_name="+")
    qty = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_cost = models.DecimalField(
        "Xarid narxi (dona)", max_digits=14, decimal_places=2, validators=[MinValueValidator(0)]
    )
    serials = models.JSONField(
        default=list, blank=True, help_text='[{"serial_number": "...", "imei1": "..."}]'
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.variant} x{self.qty}"


class StockTransfer(_Document):
    PREFIX = "KO"
    source = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="+")
    target = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="+")

    class Meta(_Document.Meta):
        verbose_name = "ko'chirish"
        verbose_name_plural = "ko'chirishlar"
        constraints = [
            models.CheckConstraint(condition=~Q(source=models.F("target")), name="transfer_diff_wh")
        ]


class StockTransferLine(models.Model):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT, related_name="+")
    qty = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    serial_ids = models.JSONField(default=list, blank=True, help_text="Ko'chiriladigan SerialUnit ID'lari")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.variant} x{self.qty}"


class WriteOff(_Document):
    class Reason(models.TextChoices):
        DEFECT = "defect", "Nuqson (brak)"
        DAMAGED = "damaged", "Shikastlangan"
        LOST = "lost", "Yo'qolgan"
        RETURN_TO_SUPPLIER = "supplier_return", "Ta'minotchiga qaytarildi"
        OTHER = "other", "Boshqa"

    PREFIX = "HC"
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=16, choices=Reason.choices)
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.PROTECT, related_name="returns"
    )

    class Meta(_Document.Meta):
        verbose_name = "hisobdan chiqarish"
        verbose_name_plural = "hisobdan chiqarishlar"


class WriteOffLine(models.Model):
    write_off = models.ForeignKey(WriteOff, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT, related_name="+")
    qty = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    serial_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.variant} x{self.qty}"


class CashAccount(TimeStampedModel):
    """Pul turgan joy: kassa (naqd), bank hisobi, to'lov tizimi hisobi."""

    class Kind(models.TextChoices):
        CASH = "cash", "Naqd kassa"
        BANK = "bank", "Bank hisobi"
        PAYMENT_SYSTEM = "payment_system", "To'lov tizimi"

    name = models.CharField(max_length=128, unique=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CashTransaction(models.Model):
    """Kassa yozuvi. O'chirilmaydi va o'zgartirilmaydi — xato bo'lsa teskari yozuv qilinadi (`reverses`)."""

    class Direction(models.TextChoices):
        IN = "in", "Kirim"
        OUT = "out", "Chiqim"

    class Category(models.TextChoices):
        SALE = "sale", "Sotuvdan tushum"
        COURIER_COD = "courier_cod", "Kuryerdan naqd"
        SUPPLIER_PAYMENT = "supplier_payment", "Ta'minotchiga to'lov"
        REFUND = "refund", "Xaridorga qaytarish"
        EXPENSE = "expense", "Xarajat"
        TRANSFER = "transfer", "Hisoblar orasida o'tkazma"
        CORRECTION = "correction", "Tuzatish (teskari yozuv)"
        OTHER = "other", "Boshqa"

    account = models.ForeignKey(CashAccount, on_delete=models.PROTECT, related_name="transactions")
    direction = models.CharField(max_length=3, choices=Direction.choices)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    category = models.CharField(max_length=16, choices=Category.choices)
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.PROTECT, related_name="payments"
    )
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reverses = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by"
    )
    comment = models.CharField(max_length=255, blank=True)
    occurred_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [models.Index(fields=["account", "-occurred_at"]), models.Index(fields=["category"])]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="cash_amount_gt_0"),
            models.CheckConstraint(
                condition=~Q(category="supplier_payment") | Q(supplier__isnull=False),
                name="supplier_payment_has_supplier",
            ),
        ]

    def __str__(self):
        sign = "+" if self.direction == self.Direction.IN else "-"
        return f"{self.account}: {sign}{self.amount}"
