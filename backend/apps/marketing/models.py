from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Banner(TimeStampedModel):
    """Bosh sahifa banneri. Rasm bo'lmasa — rangli fonli matnli banner."""

    title = models.JSONField(help_text='{"uz": "...", "ru": "..."}')
    subtitle = models.JSONField(default=dict, blank=True)
    image = models.FileField(upload_to="banners/", blank=True)
    image_url = models.URLField(max_length=500, blank=True)
    link = models.CharField(max_length=300, blank=True, help_text="/c/smartfonlar yoki to'liq havola")
    color = models.CharField(max_length=7, default="#5b21b6", help_text="Fon rangi (#RRGGBB)")
    sort = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort", "-id"]
        verbose_name = "banner"
        verbose_name_plural = "bannerlar"

    def __str__(self):
        return self.title.get("uz", "") if isinstance(self.title, dict) else str(self.title)

    @property
    def url(self) -> str:
        return self.image.url if self.image else self.image_url

    @classmethod
    def live(cls, now):
        return cls.objects.filter(is_active=True).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now), Q(ends_at__isnull=True) | Q(ends_at__gt=now)
        )


class SiteContent(models.Model):
    """Do'kon sahifalari matni va tuzilishi (bitta yozuv): aloqa, e'lon, bosh sahifa bo'limlari, futer,
    ma'lumot sahifalari. Tuzilishi va standart qiymatlari — services.SITE_DEFAULTS."""

    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sayt matnlari"
        verbose_name_plural = "Sayt matnlari"

    def __str__(self):
        return "Sayt matnlari"


class PromoCode(TimeStampedModel):
    """Promokod: tovarlar summasiga chegirma (foiz yoki so'mda). Yetkazish narxiga ta'sir qilmaydi."""

    class Kind(models.TextChoices):
        PERCENT = "percent", "Foiz"
        AMOUNT = "amount", "So'm"

    code = models.CharField(max_length=32, unique=True, help_text="Katta harflarda saqlanadi")
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField(max_digits=14, decimal_places=2)
    min_subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    max_discount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, help_text="Foizli kod uchun yuqori chegara"
    )
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Jami necha marta")
    once_per_customer = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "promokod"
        verbose_name_plural = "promokodlar"

    def __str__(self):
        return self.code


class StockRequest(TimeStampedModel):
    """ "Kelganda xabar bering": tugagan tovar uchun mijoz qoldirgan telefon."""

    class Status(models.TextChoices):
        NEW = "new", "Kutilmoqda"
        NOTIFIED = "notified", "Xabar berildi"
        CANCELLED = "cancelled", "Bekor qilindi"

    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.CASCADE, related_name="+")
    phone = models.CharField(max_length=16)
    name = models.CharField(max_length=80, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["status", "variant"])]
        verbose_name = "kelganda xabar so'rovi"
        verbose_name_plural = "kelganda xabar so'rovlari"


class QuickOrder(TimeStampedModel):
    """1 bosishda xarid: mijoz faqat telefon qoldiradi, qolganini operator qo'ng'iroq qilib aniqlaydi."""

    class Status(models.TextChoices):
        NEW = "new", "Yangi"
        DONE = "done", "Bog'lanildi"
        CANCELLED = "cancelled", "Bekor qilindi"

    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT, related_name="+")
    qty = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=14, decimal_places=2, help_text="So'rov paytidagi narx")
    phone = models.CharField(max_length=16)
    name = models.CharField(max_length=80, blank=True)
    comment = models.CharField(max_length=300, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-id"]
        verbose_name = "tez buyurtma"
        verbose_name_plural = "tez buyurtmalar"
