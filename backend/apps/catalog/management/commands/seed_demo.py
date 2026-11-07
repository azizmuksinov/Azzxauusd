"""Demo katalog: kategoriyalar, xususiyatlar, tovarlar, qoldiq. Qayta ishga tushirish xavfsiz (idempotent).

FAQAT demo/dev uchun: narxlar va qoldiqlar soxta.
"""

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeValue,
    Brand,
    Category,
    CategoryAttribute,
    Product,
    ProductVariant,
)
from apps.core.translit import latin_to_cyrillic
from apps.inventory.models import Stock, Warehouse


def t(uz, ru):
    return {"uz": uz, "uz_cyrl": latin_to_cyrillic(uz), "ru": ru}


CATEGORIES = [
    ("elektronika", None, t("Elektronika", "Электроника")),
    ("smartfonlar", "elektronika", t("Smartfonlar", "Смартфоны")),
    ("televizorlar", "elektronika", t("Televizorlar", "Телевизоры")),
    ("noutbuklar", "elektronika", t("Noutbuklar", "Ноутбуки")),
    ("maishiy-texnika", None, t("Maishiy texnika", "Бытовая техника")),
    ("muzlatkichlar", "maishiy-texnika", t("Muzlatkichlar", "Холодильники")),
    ("kir-yuvish-mashinalari", "maishiy-texnika", t("Kir yuvish mashinalari", "Стиральные машины")),
    ("konditsionerlar", "maishiy-texnika", t("Konditsionerlar", "Кондиционеры")),
]

# code, name, group, type, unit, filterable, categories, options
ATTRIBUTES = [
    (
        "memory",
        t("Ichki xotira", "Встроенная память"),
        t("Xotira", "Память"),
        "enum",
        "",
        True,
        ["smartfonlar"],
        [("128", t("128 GB", "128 ГБ")), ("256", t("256 GB", "256 ГБ")), ("512", t("512 GB", "512 ГБ"))],
    ),
    (
        "color",
        t("Rang", "Цвет"),
        t("Umumiy", "Общие"),
        "enum",
        "",
        True,
        ["elektronika", "maishiy-texnika"],
        [
            ("black", t("Qora", "Чёрный")),
            ("white", t("Oq", "Белый")),
            ("silver", t("Kumushrang", "Серебристый")),
            ("blue", t("Ko'k", "Синий")),
        ],
    ),
    (
        "screen_size",
        t("Ekran diagonali", "Диагональ экрана"),
        t("Ekran", "Экран"),
        "number",
        "dyuym",
        True,
        ["smartfonlar", "televizorlar", "noutbuklar"],
        [],
    ),
    (
        "smart_tv",
        t("Smart TV", "Smart TV"),
        t("Imkoniyatlar", "Возможности"),
        "bool",
        "",
        True,
        ["televizorlar"],
        [],
    ),
    (
        "ram",
        t("Operativ xotira", "Оперативная память"),
        t("Xotira", "Память"),
        "number",
        "GB",
        True,
        ["noutbuklar", "smartfonlar"],
        [],
    ),
    (
        "volume",
        t("Umumiy hajm", "Общий объём"),
        t("Asosiy", "Основные"),
        "number",
        "l",
        True,
        ["muzlatkichlar"],
        [],
    ),
    ("no_frost", t("No Frost", "No Frost"), t("Asosiy", "Основные"), "bool", "", True, ["muzlatkichlar"], []),
    (
        "load_kg",
        t("Maksimal yuklama", "Максимальная загрузка"),
        t("Asosiy", "Основные"),
        "number",
        "kg",
        True,
        ["kir-yuvish-mashinalari"],
        [],
    ),
    (
        "area_m2",
        t("Xona maydoni", "Площадь помещения"),
        t("Asosiy", "Основные"),
        "number",
        "m²",
        True,
        ["konditsionerlar"],
        [],
    ),
    (
        "inverter",
        t("Inverter", "Инвертор"),
        t("Asosiy", "Основные"),
        "bool",
        "",
        True,
        ["konditsionerlar", "muzlatkichlar", "kir-yuvish-mashinalari"],
        [],
    ),
]

# slug, category, brand, name_uz, name_ru, bulky, warranty, attrs,
# variants: [(sku, suffix_uz, suffix_ru, price, old_price, qty, variant_attrs)]
PRODUCTS = [
    (
        "samsung-galaxy-a55",
        "smartfonlar",
        "Samsung",
        "Samsung Galaxy A55",
        "Samsung Galaxy A55",
        False,
        12,
        {"screen_size": 6.6, "ram": 8, "color": "blue"},
        [
            ("DEMO-SGA55-128", "128 GB", "128 ГБ", 4590000, 4990000, 12, {"memory": "128"}),
            ("DEMO-SGA55-256", "256 GB", "256 ГБ", 5290000, None, 4, {"memory": "256"}),
        ],
    ),
    (
        "apple-iphone-15",
        "smartfonlar",
        "Apple",
        "Apple iPhone 15",
        "Apple iPhone 15",
        False,
        12,
        {"screen_size": 6.1, "ram": 6, "color": "black"},
        [
            ("DEMO-IP15-128", "128 GB", "128 ГБ", 10990000, 11990000, 6, {"memory": "128"}),
            ("DEMO-IP15-256", "256 GB", "256 ГБ", 12590000, None, 2, {"memory": "256"}),
        ],
    ),
    (
        "xiaomi-redmi-note-13",
        "smartfonlar",
        "Xiaomi",
        "Xiaomi Redmi Note 13",
        "Xiaomi Redmi Note 13",
        False,
        12,
        {"screen_size": 6.67, "ram": 8, "color": "black"},
        [("DEMO-RN13-256", "256 GB", "256 ГБ", 2790000, 3190000, 25, {"memory": "256"})],
    ),
    (
        "samsung-qled-55-q60",
        "televizorlar",
        "Samsung",
        'Samsung QLED 55" Q60 televizori',
        'Телевизор Samsung QLED 55" Q60',
        True,
        24,
        {"screen_size": 55, "smart_tv": True, "color": "black"},
        [("DEMO-TV-SQ55", "", "", 8990000, 9990000, 5, {})],
    ),
    (
        "lg-oled-65-c3",
        "televizorlar",
        "LG",
        'LG OLED 65" C3 televizori',
        'Телевизор LG OLED 65" C3',
        True,
        24,
        {"screen_size": 65, "smart_tv": True, "color": "black"},
        [("DEMO-TV-LGC65", "", "", 21990000, None, 2, {})],
    ),
    (
        "artel-43-ua43h3502",
        "televizorlar",
        "Artel",
        'Artel 43" televizori',
        'Телевизор Artel 43"',
        True,
        12,
        {"screen_size": 43, "smart_tv": False, "color": "black"},
        [("DEMO-TV-AR43", "", "", 2890000, 3290000, 15, {})],
    ),
    (
        "lenovo-ideapad-slim-3",
        "noutbuklar",
        "Lenovo",
        "Lenovo IdeaPad Slim 3 noutbuki",
        "Ноутбук Lenovo IdeaPad Slim 3",
        False,
        12,
        {"screen_size": 15.6, "ram": 16, "color": "silver"},
        [("DEMO-NB-LIS3", "", "", 7490000, None, 7, {})],
    ),
    (
        "hp-15-fd0000",
        "noutbuklar",
        "HP",
        "HP 15 noutbuki",
        "Ноутбук HP 15",
        False,
        12,
        {"screen_size": 15.6, "ram": 8, "color": "silver"},
        [("DEMO-NB-HP15", "", "", 5990000, 6490000, 0, {})],
    ),
    (
        "artel-hd-455-rwenf",
        "muzlatkichlar",
        "Artel",
        "Artel HD 455 RWENF muzlatkichi",
        "Холодильник Artel HD 455 RWENF",
        True,
        36,
        {"volume": 346, "no_frost": True, "inverter": False, "color": "white"},
        [("DEMO-FR-AR455", "", "", 5490000, 5990000, 8, {})],
    ),
    (
        "samsung-rb38",
        "muzlatkichlar",
        "Samsung",
        "Samsung RB38 muzlatkichi",
        "Холодильник Samsung RB38",
        True,
        24,
        {"volume": 385, "no_frost": True, "inverter": True, "color": "silver"},
        [("DEMO-FR-SRB38", "", "", 9990000, None, 3, {})],
    ),
    (
        "lg-f2v5hs0w",
        "kir-yuvish-mashinalari",
        "LG",
        "LG F2V5HS0W kir yuvish mashinasi",
        "Стиральная машина LG F2V5HS0W",
        True,
        24,
        {"load_kg": 7, "inverter": True, "color": "white"},
        [("DEMO-WM-LG7", "", "", 5190000, 5690000, 6, {})],
    ),
    (
        "artel-wf60",
        "kir-yuvish-mashinalari",
        "Artel",
        "Artel WF60 kir yuvish mashinasi",
        "Стиральная машина Artel WF60",
        True,
        36,
        {"load_kg": 6, "inverter": False, "color": "white"},
        [("DEMO-WM-AR6", "", "", 2990000, None, 10, {})],
    ),
    (
        "artel-12-inverter",
        "konditsionerlar",
        "Artel",
        "Artel 12 inverter konditsioneri",
        "Кондиционер Artel 12 инвертор",
        True,
        36,
        {"area_m2": 35, "inverter": True, "color": "white"},
        [("DEMO-AC-AR12", "", "", 4290000, 4790000, 9, {})],
    ),
    (
        "samsung-ar09",
        "konditsionerlar",
        "Samsung",
        "Samsung AR09 konditsioneri",
        "Кондиционер Samsung AR09",
        True,
        24,
        {"area_m2": 25, "inverter": False, "color": "white"},
        [("DEMO-AC-SAR09", "", "", 4990000, None, 1, {})],
    ),
]


class Command(BaseCommand):
    help = "Demo katalog va qoldiqlarni yaratadi (faqat DEMO_MODE yoki DEBUG)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="DEMO_MODE bo'lmasa ham ishga tushirish")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not (settings.DEMO_MODE or settings.DEBUG or opts["force"]):
            raise CommandError("seed_demo faqat demo/dev muhitida ishlaydi.")

        cats = {}
        for i, (slug, parent, name) in enumerate(CATEGORIES):
            cats[slug], _ = Category.objects.update_or_create(
                slug=slug, defaults={"name": name, "parent": cats.get(parent), "sort": i}
            )

        attrs = {}
        for i, (code, name, group, dtype, unit, filterable, cat_slugs, options) in enumerate(ATTRIBUTES):
            attr, _ = Attribute.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "group_name": group,
                    "data_type": dtype,
                    "unit": unit,
                    "is_filterable": filterable,
                    "sort": i,
                },
            )
            for j, (ocode, oname) in enumerate(options):
                AttributeOption.objects.update_or_create(
                    attribute=attr, code=ocode, defaults={"value": oname, "sort": j}
                )
            for cs in cat_slugs:
                CategoryAttribute.objects.get_or_create(category=cats[cs], attribute=attr)
            attrs[code] = attr

        warehouse, _ = Warehouse.objects.get_or_create(
            code="toshkent-1", defaults={"name": "Toshkent markaziy ombori"}
        )

        for slug, cat, brand_name, name_uz, name_ru, bulky, warranty, pattrs, variants in PRODUCTS:
            brand, _ = Brand.objects.get_or_create(slug=brand_name.lower(), defaults={"name": brand_name})
            product, _ = Product.objects.update_or_create(
                slug=slug,
                defaults={
                    "category": cats[cat],
                    "brand": brand,
                    "name": t(name_uz, name_ru),
                    "description": t(f"{name_uz} — demo tavsif.", f"{name_ru} — демо описание."),
                    "status": Product.Status.ACTIVE,
                    "is_bulky": bulky,
                    "warranty_months": warranty,
                    "serial_tracking": Product.SerialTracking.NONE,
                    "mxik_code": "DEMO",
                },
            )
            for code, value in pattrs.items():
                self._set(product, None, attrs[code], value)
            for sort, (sku, suf_uz, suf_ru, price, old, qty, vattrs) in enumerate(variants):
                variant, _ = ProductVariant.objects.update_or_create(
                    sku=sku,
                    defaults={
                        "product": product,
                        "name_suffix": t(suf_uz, suf_ru) if suf_uz else {},
                        "price": Decimal(price),
                        "old_price": Decimal(old) if old else None,
                        "cost_price": Decimal(price) * Decimal("0.82"),
                        "sort": sort,
                        "weight_kg": Decimal("40") if bulky else Decimal("0.5"),
                    },
                )
                for code, value in vattrs.items():
                    self._set(product, variant, attrs[code], value)
                Stock.objects.update_or_create(
                    warehouse=warehouse, variant=variant, defaults={"on_hand": qty}
                )

        self._seed_delivery()
        self.stdout.write(
            self.style.SUCCESS(f"Demo: {len(PRODUCTS)} ta tovar, {len(CATEGORIES)} ta kategoriya.")
        )

    @staticmethod
    def _seed_delivery():
        """Demo yetkazish tariflari (SOXTA narxlar). Haqiqiy tariflar admin panelda kiritiladi."""
        from apps.core.settings_registry import set_setting
        from apps.geo.models import Region
        from apps.geo.seed_data import REGIONS
        from apps.logistics.models import DeliveryTariff, DeliveryZone

        zones = [
            (
                "DEMO: Toshkent shahri",
                ["1726"],
                1,
                2,
                [("standard", "5", 25000), ("standard", None, 40000), ("truck", None, 120000)],
            ),
            (
                "DEMO: Viloyatlar",
                [r for r, *_ in REGIONS if r != "1726"],
                2,
                5,
                [("standard", "5", 45000), ("standard", None, 70000), ("truck", None, 250000)],
            ),
        ]
        for sort, (name, soatos, eta_min, eta_max, tariffs) in enumerate(zones):
            zone, _ = DeliveryZone.objects.update_or_create(
                name=name, defaults={"eta_days_min": eta_min, "eta_days_max": eta_max, "sort": sort}
            )
            zone.regions.set(Region.objects.filter(soato_code__in=soatos))
            for vehicle, max_kg, price in tariffs:
                DeliveryTariff.objects.update_or_create(
                    zone=zone,
                    vehicle=vehicle,
                    max_weight_kg=Decimal(max_kg) if max_kg else None,
                    defaults={"price": Decimal(price)},
                )
        set_setting("lifting_price_per_floor", "15000")
        set_setting("lifting_price_with_elevator", "30000")

    @staticmethod
    def _set(product, variant, attr, value):
        defaults = {"option": None, "value_number": None, "value_bool": None, "value_text": None}
        if attr.data_type == Attribute.DataType.ENUM:
            defaults["option"] = attr.options.get(code=value)
        elif attr.data_type == Attribute.DataType.NUMBER:
            defaults["value_number"] = Decimal(str(value))
        elif attr.data_type == Attribute.DataType.BOOL:
            defaults["value_bool"] = value
        AttributeValue.objects.update_or_create(
            product=product, variant=variant, attribute=attr, defaults=defaults
        )
