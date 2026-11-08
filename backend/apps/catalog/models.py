from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.i18n import LANG_KEYS, localize
from apps.core.models import TimeStampedModel
from apps.core.translit import latin_to_cyrillic


def i18n_values(value: dict | None) -> list[str]:
    """i18n maydonning barcha tillardagi matnlari (+ lotindan kirill), qidiruv uchun."""
    if not value:
        return []
    out = [value.get(k) for k in LANG_KEYS if value.get(k)]
    if value.get("uz") and not value.get("uz_cyrl"):
        out.append(latin_to_cyrillic(value["uz"]))
    return out


class Category(TimeStampedModel):
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    slug = models.SlugField(max_length=128, unique=True)
    name = models.JSONField()
    icon = models.CharField(max_length=255, blank=True)
    sort = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    attributes = models.ManyToManyField("Attribute", through="CategoryAttribute", related_name="categories")

    class Meta:
        ordering = ["sort", "id"]
        verbose_name_plural = "categories"

    def __str__(self):
        return localize(self.name, "uz")

    def descendant_ids(self) -> list[int]:
        """O'zi va barcha ichki kategoriyalar ID'lari (daraxt kichik — bir nechta so'rov yetadi)."""
        ids, frontier = [self.id], [self.id]
        while frontier:
            frontier = list(Category.objects.filter(parent_id__in=frontier).values_list("id", flat=True))
            ids.extend(frontier)
        return ids

    def ancestors(self) -> list["Category"]:
        chain, node = [], self
        while node is not None:
            chain.append(node)
            node = node.parent
        return list(reversed(chain))


class Brand(TimeStampedModel):
    slug = models.SlugField(max_length=128, unique=True)
    name = models.CharField(max_length=128)
    logo = models.FileField(upload_to="brands/", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Attribute(TimeStampedModel):
    class DataType(models.TextChoices):
        NUMBER = "number", "Son"
        TEXT = "text", "Matn"
        BOOL = "bool", "Ha/Yo'q"
        ENUM = "enum", "Ro'yxat"

    code = models.SlugField(max_length=64, unique=True)
    name = models.JSONField()
    group_name = models.JSONField(default=dict, blank=True, help_text="Ekran, Xotira, ...")
    data_type = models.CharField(max_length=8, choices=DataType.choices)
    unit = models.CharField(max_length=16, blank=True)
    is_filterable = models.BooleanField(default=False)
    is_comparable = models.BooleanField(default=True)
    sort = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort", "id"]

    def __str__(self):
        return self.code


class AttributeOption(models.Model):
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name="options")
    code = models.SlugField(max_length=64)
    value = models.JSONField()
    sort = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort", "id"]
        constraints = [models.UniqueConstraint(fields=["attribute", "code"], name="uniq_attr_option_code")]

    def __str__(self):
        return f"{self.attribute.code}={self.code}"


class CategoryAttribute(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE)
    is_required = models.BooleanField(default=False)
    sort = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort", "id"]
        constraints = [
            models.UniqueConstraint(fields=["category", "attribute"], name="uniq_category_attribute")
        ]

    def __str__(self):
        return f"{self.category_id}:{self.attribute_id}"


class Product(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Qoralama"
        ACTIVE = "active", "Sotuvda"
        ARCHIVED = "archived", "Arxiv"

    class SerialTracking(models.TextChoices):
        NONE = "none", "Yo'q"
        SERIAL = "serial", "Seriya raqam"
        IMEI = "imei", "IMEI"
        IMEI2 = "imei2", "2 ta IMEI"

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.PROTECT, related_name="products")
    slug = models.SlugField(max_length=200, unique=True)
    name = models.JSONField()
    description = models.JSONField(default=dict, blank=True)
    model_code = models.CharField(max_length=64, blank=True)
    video_url = models.URLField(
        max_length=500, blank=True, help_text="YouTube havolasi yoki to'g'ridan-to'g'ri .mp4 fayl"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    warranty_months = models.PositiveSmallIntegerField(default=12)
    is_bulky = models.BooleanField(default=False, help_text="Yirik texnika: yuk mashinasi, qavatga ko'tarish")
    serial_tracking = models.CharField(
        max_length=8, choices=SerialTracking.choices, default=SerialTracking.SERIAL
    )
    # Fiskal chek uchun
    mxik_code = models.CharField("MXIK (IKPU) kodi", max_length=32, blank=True)
    package_code = models.CharField(max_length=32, blank=True)
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("12.00"))
    # reviews moduli yangilaydi
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0"))
    rating_count = models.PositiveIntegerField(default=0)
    # Denormalizatsiya: barcha tillardagi nom, brend, SKU — DB qidiruvi uchun (signal yangilaydi).
    search_text = models.TextField(blank=True, editable=False)

    class Meta:
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return localize(self.name, "uz")

    def build_search_text(self) -> str:
        parts = i18n_values(self.name)
        if self.brand_id:
            parts.append(self.brand.name)
        parts.append(self.model_code)
        parts.extend(self.variants.values_list("sku", flat=True))
        parts.extend(i18n_values(self.category.name))
        return " ".join(p for p in parts if p).lower()


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=64, unique=True)
    barcode = models.CharField(max_length=64, blank=True, db_index=True)
    name_suffix = models.JSONField(default=dict, blank=True, help_text='{"uz": "128 GB, qora"}')
    price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    old_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal("0"))
    length_cm = models.PositiveIntegerField(default=0)
    width_cm = models.PositiveIntegerField(default=0)
    height_cm = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    sort = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort", "price", "id"]
        indexes = [models.Index(fields=["product", "is_active"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(old_price__isnull=True) | Q(old_price__gt=models.F("price")),
                name="old_price_gt_price",
            )
        ]

    def __str__(self):
        return self.sku


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    variant = models.ForeignKey(
        ProductVariant, null=True, blank=True, on_delete=models.CASCADE, related_name="images"
    )
    file = models.FileField(upload_to="products/", blank=True)
    # Tashqi CDN/S3 manzili (import qilinganda). file bo'lsa — file ustun.
    external_url = models.URLField(max_length=500, blank=True)
    alt = models.JSONField(default=dict, blank=True)
    sort = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort", "id"]

    def __str__(self):
        return self.url

    @property
    def url(self) -> str:
        return self.file.url if self.file else self.external_url


class AttributeValue(models.Model):
    """Tovar (yoki aniq variant) xususiyati. variant bo'lsa — variantga xos (rang, xotira)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="attribute_values")
    variant = models.ForeignKey(
        ProductVariant, null=True, blank=True, on_delete=models.CASCADE, related_name="attribute_values"
    )
    attribute = models.ForeignKey(Attribute, on_delete=models.PROTECT, related_name="values")
    option = models.ForeignKey(AttributeOption, null=True, blank=True, on_delete=models.PROTECT)
    value_number = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    value_text = models.JSONField(null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "attribute"], condition=Q(variant__isnull=True), name="uniq_product_attr"
            ),
            models.UniqueConstraint(
                fields=["variant", "attribute"], condition=Q(variant__isnull=False), name="uniq_variant_attr"
            ),
        ]
        indexes = [
            models.Index(fields=["attribute", "option"]),
            models.Index(fields=["attribute", "value_number"]),
        ]

    def __str__(self):
        return f"{self.attribute_id}={self.display('uz')}"

    def display(self, lang: str) -> str:
        dt = self.attribute.data_type
        if dt == Attribute.DataType.ENUM and self.option_id:
            return localize(self.option.value, lang)
        if dt == Attribute.DataType.NUMBER and self.value_number is not None:
            num = self.value_number.normalize()
            text = f"{num:f}"
            return f"{text} {self.attribute.unit}".strip()
        if dt == Attribute.DataType.BOOL and self.value_bool is not None:
            return {"ru": ("Да", "Нет"), "uz_cyrl": ("Ҳа", "Йўқ")}.get(lang, ("Ha", "Yo'q"))[
                0 if self.value_bool else 1
            ]
        return (
            localize(self.value_text, lang)
            if isinstance(self.value_text, dict)
            else str(self.value_text or "")
        )


class PriceHistory(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "Qo'lda"
        EXCEL = "excel", "Excel"

    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="price_history")
    price = models.DecimalField(max_digits=14, decimal_places=2)
    old_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    source = models.CharField(max_length=8, choices=Source.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.variant_id}: {self.price}"


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="uniq_favorite")]

    def __str__(self):
        return f"{self.user_id}:{self.product_id}"


class CompareItem(models.Model):
    MAX_ITEMS = 6

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="compare_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="uniq_compare_item")]

    def __str__(self):
        return f"{self.user_id}:{self.product_id}"


class ProductImport(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Navbatda"
        RUNNING = "running", "Bajarilmoqda"
        DONE = "done", "Tugadi"
        FAILED = "failed", "Xato"

    file = models.FileField(upload_to="imports/")
    dry_run = models.BooleanField(default=False)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    rows_total = models.PositiveIntegerField(default=0)
    rows_ok = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"import #{self.pk} ({self.status})"
