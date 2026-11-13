from django.apps import AppConfig


class CatalogConfig(AppConfig):
    name = "apps.catalog"
    label = "catalog"

    def ready(self):
        from . import signals  # noqa: F401
