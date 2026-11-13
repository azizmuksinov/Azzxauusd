from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Setting(models.Model):
    """Biznes sozlamalari (admin panelda o'zgartiriladi).

    Kalitlar va standart qiymatlar — core/settings_registry.py.
    """

    key = models.CharField(max_length=64, primary_key=True)
    value = models.JSONField(null=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self):
        return self.key
