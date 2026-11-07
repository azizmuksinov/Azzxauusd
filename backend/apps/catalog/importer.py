"""Excel (.xlsx) orqali tovar va narxlarni import qilish.

Har bir qator SKU bo'yicha: variant bor bo'lsa — narx yangilanadi,
yo'q bo'lsa — tovar + variant yaratiladi.
`dry_run` — hamma narsa tekshiriladi, lekin bazaga yozilmaydi (tranzaksiya bekor qilinadi).
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db import transaction
from django.utils.text import slugify
from openpyxl import Workbook, load_workbook

from .models import Brand, Category, PriceHistory, Product, ProductImport, ProductVariant
from .services import change_price

COLUMNS = [
    ("sku", "SKU (majburiy, unikal)"),
    ("name_uz", "Nomi (lotin)"),
    ("name_ru", "Nomi (rus)"),
    ("category", "Kategoriya slug"),
    ("brand", "Brend slug yoki nomi"),
    ("price", "Narx, so'm (majburiy)"),
    ("old_price", "Eski narx, so'm"),
    ("cost_price", "Tannarx, so'm"),
    ("barcode", "Shtrix-kod"),
    ("warranty_months", "Kafolat, oy"),
    ("status", "draft | active | archived"),
]
MAX_ROWS = 5000


class RowError(Exception):
    pass


@dataclass
class ImportResult:
    total: int = 0
    ok: int = 0
    created: int = 0
    updated: int = 0
    errors: list[dict] = field(default_factory=list)


def build_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "tovarlar"
    ws.append([c for c, _ in COLUMNS])
    ws.append([d for _, d in COLUMNS])
    ws.append(
        [
            "SM-A55-128-BLK",
            "Samsung Galaxy A55 128 GB",
            "Samsung Galaxy A55 128 ГБ",
            "smartfonlar",
            "samsung",
            4990000,
            5490000,
            4200000,
            "8806095000000",
            12,
            "active",
        ]
    )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _money(raw, name: str, required: bool = False) -> Decimal | None:
    if raw in (None, ""):
        if required:
            raise RowError(f"{name} majburiy")
        return None
    try:
        value = Decimal(str(raw).replace(" ", "").replace(",", "."))
    except InvalidOperation as exc:
        raise RowError(f"{name} son emas: {raw}") from exc
    if value < 0:
        raise RowError(f"{name} manfiy")
    return value.quantize(Decimal("0.01"))


def _unique_slug(base: str) -> str:
    base = slugify(base)[:180] or "tovar"
    slug, n = base, 2
    while Product.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def _process_row(row: dict, user, result: ImportResult) -> None:
    sku = str(row.get("sku") or "").strip()
    if not sku:
        raise RowError("sku majburiy")
    price = _money(row.get("price"), "price", required=True)
    old_price = _money(row.get("old_price"), "old_price")
    cost_price = _money(row.get("cost_price"), "cost_price")
    if old_price is not None and old_price <= price:
        raise RowError("old_price narxdan katta bo'lishi kerak")
    status = (row.get("status") or "").strip() or None
    if status and status not in Product.Status.values:
        raise RowError(f"status noto'g'ri: {status}")

    variant = ProductVariant.objects.select_related("product").filter(sku=sku).first()
    if variant is None:
        name_uz = (row.get("name_uz") or "").strip()
        if not name_uz:
            raise RowError("yangi tovar uchun name_uz majburiy")
        category = Category.objects.filter(slug=(row.get("category") or "").strip()).first()
        if category is None:
            raise RowError(f"kategoriya topilmadi: {row.get('category')}")
        brand = None
        if raw_brand := (row.get("brand") or "").strip():
            brand = (
                Brand.objects.filter(slug=raw_brand).first()
                or Brand.objects.filter(name__iexact=raw_brand).first()
            )
            if brand is None:
                raise RowError(f"brend topilmadi: {raw_brand}")
        product = Product.objects.create(
            category=category,
            brand=brand,
            slug=_unique_slug(name_uz),
            name={k: v for k, v in {"uz": name_uz, "ru": (row.get("name_ru") or "").strip()}.items() if v},
            status=status or Product.Status.DRAFT,
            warranty_months=int(row.get("warranty_months") or 12),
        )
        variant = ProductVariant.objects.create(
            product=product,
            sku=sku,
            price=price,
            old_price=old_price,
            cost_price=cost_price,
            barcode=str(row.get("barcode") or ""),
        )
        PriceHistory.objects.create(
            variant=variant, price=price, old_price=old_price, source="excel", changed_by=user
        )
        result.created += 1
        return

    change_price(variant, price, old_price, source=PriceHistory.Source.EXCEL, user=user)
    fields = []
    if cost_price is not None:
        variant.cost_price = cost_price
        fields.append("cost_price")
    if row.get("barcode"):
        variant.barcode = str(row["barcode"])
        fields.append("barcode")
    if fields:
        variant.save(update_fields=[*fields, "updated_at"])
    product = variant.product
    if status and product.status != status:
        product.status = status
        product.save(update_fields=["status", "updated_at"])
    result.updated += 1


class _DryRunRollback(Exception):
    pass


def run_import(data: bytes, *, user=None, dry_run: bool = False) -> ImportResult:
    wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h else "" for h in next(rows, [])]
    if "sku" not in header or "price" not in header:
        return ImportResult(
            errors=[{"row": 1, "error": "Sarlavhada 'sku' va 'price' ustunlari bo'lishi kerak"}]
        )

    result = ImportResult()
    try:
        with transaction.atomic():
            for idx, values in enumerate(rows, start=2):
                row = dict(zip(header, values, strict=False))
                if not any(v not in (None, "") for v in row.values()):
                    continue
                if row.get("sku") == COLUMNS[0][1]:  # shablondagi izoh qatori
                    continue
                result.total += 1
                if result.total > MAX_ROWS:
                    result.errors.append({"row": idx, "error": f"Ko'pi bilan {MAX_ROWS} qator"})
                    break
                try:
                    with transaction.atomic():
                        _process_row(row, user, result)
                    result.ok += 1
                except RowError as exc:
                    result.errors.append({"row": idx, "sku": row.get("sku"), "error": str(exc)})
                except Exception as exc:  # noqa: BLE001 - qator xatosi butun importni to'xtatmasin
                    result.errors.append(
                        {"row": idx, "sku": row.get("sku"), "error": f"Kutilmagan xato: {exc}"}
                    )
            if dry_run:
                raise _DryRunRollback
    except _DryRunRollback:
        pass
    return result


def run_import_job(job: ProductImport) -> ProductImport:
    job.status = ProductImport.Status.RUNNING
    job.save(update_fields=["status", "updated_at"])
    try:
        with job.file.open("rb") as fh:
            result = run_import(fh.read(), user=job.created_by, dry_run=job.dry_run)
    except Exception as exc:  # noqa: BLE001
        job.status = ProductImport.Status.FAILED
        job.errors = [{"row": None, "error": f"Faylni o'qib bo'lmadi: {exc}"}]
        job.save(update_fields=["status", "errors", "updated_at"])
        return job
    job.status = ProductImport.Status.DONE
    job.rows_total, job.rows_ok, job.rows_failed = result.total, result.ok, len(result.errors)
    job.errors = result.errors[:500]
    job.save()
    return job
