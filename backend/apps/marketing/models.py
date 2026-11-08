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
