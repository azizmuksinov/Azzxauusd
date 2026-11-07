from django.db import migrations

from apps.core.translit import latin_to_cyrillic
from apps.geo.seed_data import REGIONS, TASHKENT_CITY_DISTRICTS


def i18n(uz: str, ru: str) -> dict:
    return {"uz": uz, "uz_cyrl": latin_to_cyrillic(uz), "ru": ru}


def seed(apps, schema_editor):
    Region = apps.get_model("geo", "Region")
    District = apps.get_model("geo", "District")
    for sort, (soato, uz, ru) in enumerate(REGIONS):
        region, _ = Region.objects.update_or_create(
            soato_code=soato, defaults={"name": i18n(uz, ru), "sort": sort}
        )
        if soato == "1726":
            for d_uz, d_ru in TASHKENT_CITY_DISTRICTS:
                if not District.objects.filter(region=region, name__uz=d_uz).exists():
                    District.objects.create(region=region, name=i18n(d_uz, d_ru))


class Migration(migrations.Migration):
    dependencies = [("geo", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
