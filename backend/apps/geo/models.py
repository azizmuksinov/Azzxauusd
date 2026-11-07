from django.db import models

from apps.core.i18n import localize


class Region(models.Model):
    name = models.JSONField(help_text='{"uz": ..., "uz_cyrl": ..., "ru": ...}')
    soato_code = models.CharField(max_length=10, unique=True)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort", "id"]

    def __str__(self):
        return localize(self.name, "uz")


class District(models.Model):
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="districts")
    name = models.JSONField()
    soato_code = models.CharField(max_length=10, unique=True, null=True, blank=True)
    # Yetkazish provayderlarining o'z ma'lumotnomalaridagi kodlar (logistics moduli to'ldiradi).
    bts_city_code = models.CharField(max_length=32, blank=True)
    fargo_city_code = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["region_id", "id"]

    def __str__(self):
        return localize(self.name, "uz")
