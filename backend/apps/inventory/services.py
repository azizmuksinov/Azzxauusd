"""Qoldiq bilan barcha operatsiyalar faqat shu yerdan o'tadi.

Qoidalar:
- Har bir o'zgarish `Stock` qatorini `select_for_update` bilan qulflaydi va `StockMovement` yozadi.
- Qulflash tartibi deterministik (stock.id bo'yicha) — deadlock bo'lmasligi uchun.
- available = on_hand - reserved; DB cheklovlari manfiy qoldiq va reserved > on_hand ga yo'l qo'ymaydi.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.catalog.models import Product, ProductVariant
from apps.core.exceptions import ApiError

from .imei import is_valid_imei
from .models import Reservation, SerialUnit, Stock, StockMovement, Warehouse


class OutOfStock(ApiError):
    status_code = 409
    default_code = "out_of_stock"
    default_detail = "Omborda yetarli tovar yo'q."


class InventoryError(ApiError):
    default_code = "inventory_error"


@dataclass(frozen=True)
class SerialInput:
    serial_number: str = ""
    imei1: str | None = None
    imei2: str | None = None


def _locked_stock(warehouse: Warehouse, variant: ProductVariant) -> Stock:
    Stock.objects.get_or_create(warehouse=warehouse, variant=variant)
    return Stock.objects.select_for_update().get(warehouse=warehouse, variant=variant)


def _movement(stock: Stock, delta: int, reason: str, *, user=None, ref=("", ""), comment="") -> None:
    StockMovement.objects.create(
        warehouse_id=stock.warehouse_id,
        variant_id=stock.variant_id,
        delta=delta,
        on_hand_after=stock.on_hand,
        reason=reason,
        ref_type=ref[0],
        ref_id=str(ref[1]),
        comment=comment[:255],
        created_by=user,
    )


def _validate_serials(variant: ProductVariant, qty: int, serials: list[SerialInput]) -> None:
    tracking = variant.product.serial_tracking
    if tracking == Product.SerialTracking.NONE:
        if serials:
            raise InventoryError(message="Bu tovar seriya raqam bilan hisoblanmaydi.")
        return
    if len(serials) != qty:
        raise InventoryError(
            "serials_count_mismatch", f"Seriya raqamlar soni ({len(serials)}) miqdorga ({qty}) teng emas."
        )
    seen: set[str] = set()
    for s in serials:
        keys = [k for k in (s.serial_number, s.imei1, s.imei2) if k]
        if not keys:
            raise InventoryError("serial_required", "Har bir dona uchun seriya raqam yoki IMEI kerak.")
        if tracking in (Product.SerialTracking.IMEI, Product.SerialTracking.IMEI2) and not s.imei1:
            raise InventoryError("imei_required", "Bu tovar uchun IMEI majburiy.")
        if tracking == Product.SerialTracking.IMEI2 and not s.imei2:
            raise InventoryError("imei_required", "Bu tovar uchun ikkinchi IMEI ham majburiy.")
        for imei in (s.imei1, s.imei2):
            if imei and not is_valid_imei(imei):
                raise InventoryError("imei_invalid", f"IMEI noto'g'ri: {imei}")
        for k in keys:
            if k in seen:
                raise InventoryError("serial_duplicate", f"Takroriy raqam: {k}")
            seen.add(k)


@transaction.atomic
def receive(
    warehouse: Warehouse,
    variant: ProductVariant,
    qty: int,
    *,
    serials: Iterable[SerialInput] = (),
    user=None,
    ref=("", ""),
    comment: str = "",
) -> Stock:
    """Kirim. Seriyali tovarlarda har bir dona `SerialUnit` sifatida yaratiladi."""
    if qty <= 0:
        raise InventoryError(message="Miqdor musbat bo'lishi kerak.")
    serials = list(serials)
    _validate_serials(variant, qty, serials)

    imeis = [i for s in serials for i in (s.imei1, s.imei2) if i]
    if imeis and SerialUnit.objects.filter(Q(imei1__in=imeis) | Q(imei2__in=imeis)).exists():
        raise InventoryError("serial_duplicate", "Bu IMEI tizimda allaqachon bor.")
    numbers = [s.serial_number for s in serials if s.serial_number]
    if numbers and SerialUnit.objects.filter(variant=variant, serial_number__in=numbers).exists():
        raise InventoryError("serial_duplicate", "Bu seriya raqam tizimda allaqachon bor.")

    now = timezone.now().isoformat()
    SerialUnit.objects.bulk_create(
        [
            SerialUnit(
                variant=variant,
                warehouse=warehouse,
                serial_number=s.serial_number,
                imei1=s.imei1 or None,
                imei2=s.imei2 or None,
                history=[
                    {
                        "at": now,
                        "status": "in_stock",
                        "ref": f"{ref[0]}:{ref[1]}",
                        "by": getattr(user, "pk", None),
                    }
                ],
            )
            for s in serials
        ]
    )

    stock = _locked_stock(warehouse, variant)
    stock.on_hand = F("on_hand") + qty
    stock.save(update_fields=["on_hand", "updated_at"])
    stock.refresh_from_db()
    _movement(stock, qty, StockMovement.Reason.RECEIPT, user=user, ref=ref, comment=comment)
    return stock


@transaction.atomic
def adjust(
    warehouse: Warehouse, variant: ProductVariant, new_on_hand: int, *, user=None, comment: str
) -> Stock:
    """Inventarizatsiya natijasi: haqiqiy qoldiqni o'rnatish. Band qilingandan kam bo'lishi mumkin emas."""
    if not comment:
        raise InventoryError(message="Tuzatish sababini yozing.")
    stock = _locked_stock(warehouse, variant)
    if new_on_hand < stock.reserved:
        raise InventoryError(
            "below_reserved", f"Qoldiq band qilingan miqdordan ({stock.reserved}) kam bo'lishi mumkin emas."
        )
    delta = new_on_hand - stock.on_hand
    if delta:
        stock.on_hand = new_on_hand
        stock.save(update_fields=["on_hand", "updated_at"])
        _movement(stock, delta, StockMovement.Reason.ADJUSTMENT, user=user, comment=comment)
    return stock


def _take_serials(warehouse: Warehouse, variant: ProductVariant, qty: int, serial_ids) -> list[SerialUnit]:
    """Chiqim uchun seriyali donalar: soni miqdorga teng, hammasi shu omborda va `in_stock`."""
    if variant.product.serial_tracking == Product.SerialTracking.NONE:
        if serial_ids:
            raise InventoryError(message="Bu tovar seriya raqam bilan hisoblanmaydi.")
        return []
    ids = list(dict.fromkeys(serial_ids))
    if len(ids) != qty:
        raise InventoryError("serials_count_mismatch", f"{qty} ta dona uchun {qty} ta seriya raqam tanlang.")
    units = list(
        SerialUnit.objects.select_for_update().filter(
            pk__in=ids, variant=variant, warehouse=warehouse, status=SerialUnit.Status.IN_STOCK
        )
    )
    if len(units) != qty:
        raise InventoryError("serial_unavailable", "Tanlangan seriya raqamlar shu omborda mavjud emas.")
    return units


def _serial_history(unit: SerialUnit, status: str, ref, user) -> None:
    unit.history = [
        *unit.history,
        {
            "at": timezone.now().isoformat(),
            "status": status,
            "ref": f"{ref[0]}:{ref[1]}",
            "by": getattr(user, "pk", None),
        },
    ]


@transaction.atomic
def issue(
    warehouse: Warehouse,
    variant: ProductVariant,
    qty: int,
    *,
    reason: str,
    serial_ids=(),
    user=None,
    ref=("", ""),
    comment: str = "",
) -> Stock:
    """Chiqim (hisobdan chiqarish va h.k.): faqat band qilinmagan qoldiqdan."""
    if qty <= 0:
        raise InventoryError(message="Miqdor musbat bo'lishi kerak.")
    stock = _locked_stock(warehouse, variant)
    if stock.available < qty:
        raise OutOfStock(
            extra={
                "items": [
                    {
                        "variant_id": variant.id,
                        "sku": variant.sku,
                        "requested": qty,
                        "available": stock.available,
                    }
                ]
            }
        )
    for unit in _take_serials(warehouse, variant, qty, serial_ids):
        unit.status = SerialUnit.Status.WRITTEN_OFF
        unit.warehouse = None
        _serial_history(unit, unit.status, ref, user)
        unit.save(update_fields=["status", "warehouse", "history", "updated_at"])
    stock.on_hand = F("on_hand") - qty
    stock.save(update_fields=["on_hand", "updated_at"])
    stock.refresh_from_db()
    _movement(stock, -qty, reason, user=user, ref=ref, comment=comment)
    return stock


@transaction.atomic
def transfer(
    source: Warehouse,
    target: Warehouse,
    variant: ProductVariant,
    qty: int,
    *,
    serial_ids=(),
    user=None,
    ref=("", ""),
    comment: str = "",
) -> tuple[Stock, Stock]:
    """Omborlar orasida ko'chirish: manbadan bo'sh qoldiq kamayadi, maqsadda ko'payadi; seriyalar ko'chadi."""
    if source.pk == target.pk:
        raise InventoryError(message="Manba va maqsad ombor bir xil.")
    if qty <= 0:
        raise InventoryError(message="Miqdor musbat bo'lishi kerak.")
    first, second = sorted([source, target], key=lambda w: w.pk)  # deadlock bo'lmasligi uchun tartib
    locked = {first.pk: _locked_stock(first, variant), second.pk: _locked_stock(second, variant)}
    src, dst = locked[source.pk], locked[target.pk]
    if src.available < qty:
        raise OutOfStock(
            extra={
                "items": [
                    {
                        "variant_id": variant.id,
                        "sku": variant.sku,
                        "requested": qty,
                        "available": src.available,
                    }
                ]
            }
        )
    for unit in _take_serials(source, variant, qty, serial_ids):
        unit.warehouse = target
        _serial_history(unit, "transferred", ref, user)
        unit.save(update_fields=["warehouse", "history", "updated_at"])
    src.on_hand = F("on_hand") - qty
    src.save(update_fields=["on_hand", "updated_at"])
    dst.on_hand = F("on_hand") + qty
    dst.save(update_fields=["on_hand", "updated_at"])
    src.refresh_from_db()
    dst.refresh_from_db()
    _movement(src, -qty, StockMovement.Reason.TRANSFER_OUT, user=user, ref=ref, comment=comment)
    _movement(dst, qty, StockMovement.Reason.TRANSFER_IN, user=user, ref=ref, comment=comment)
    return src, dst


def available_by_variant(variant_ids: Iterable[int]) -> dict[int, int]:
    rows = (
        Stock.objects.filter(
            variant_id__in=list(variant_ids), warehouse__is_active=True, warehouse__is_sellable=True
        )
        .values("variant_id")
        .annotate(av=Sum(F("on_hand") - F("reserved")))
    )
    return {r["variant_id"]: max(r["av"] or 0, 0) for r in rows}


@transaction.atomic
def reserve(
    ref_type: str, ref_id, items: Iterable[tuple[ProductVariant, int]], *, expires_at=None
) -> list[Reservation]:
    """Bir nechta pozitsiyani band qilish: hammasi yoki hech biri.

    Har bir variant uchun omborlar eng ko'p bo'sh qoldiq tartibida tanlanadi (kerak bo'lsa bo'linadi).
    """
    items = [(v, q) for v, q in items if q > 0]
    variant_ids = sorted({v.id for v, _ in items})
    stocks = list(
        Stock.objects.select_for_update(of=("self",))
        .filter(variant_id__in=variant_ids, warehouse__is_active=True, warehouse__is_sellable=True)
        .order_by("id")
    )
    by_variant: dict[int, list[Stock]] = {}
    for s in stocks:
        by_variant.setdefault(s.variant_id, []).append(s)

    shortages = []
    plan: list[tuple[Stock, int]] = []
    for variant, qty in items:
        candidates = sorted(by_variant.get(variant.id, []), key=lambda s: s.available, reverse=True)
        need = qty
        for s in candidates:
            take = min(need, s.available)
            if take > 0:
                plan.append((s, take))
                s.reserved += take  # keyingi pozitsiya uchun lokal holat
                need -= take
            if need == 0:
                break
        if need:
            shortages.append(
                {"variant_id": variant.id, "sku": variant.sku, "requested": qty, "missing": need}
            )
    if shortages:
        raise OutOfStock(extra={"items": shortages})

    reservations = []
    for stock, qty in plan:
        Stock.objects.filter(pk=stock.pk).update(reserved=F("reserved") + qty, updated_at=timezone.now())
        reservations.append(
            Reservation.objects.create(
                warehouse_id=stock.warehouse_id,
                variant_id=stock.variant_id,
                qty=qty,
                ref_type=ref_type,
                ref_id=str(ref_id),
                expires_at=expires_at,
            )
        )
    return reservations


def _active_reservations(ref_type: str, ref_id):
    return list(
        Reservation.objects.select_for_update()
        .filter(ref_type=ref_type, ref_id=str(ref_id), status=Reservation.Status.ACTIVE)
        .order_by("id")
    )


@transaction.atomic
def release(ref_type: str, ref_id) -> int:
    """Bandni bekor qilish (buyurtma bekor bo'ldi / to'lov muddati o'tdi). Qaytaradi: bo'shatilgan dona."""
    total = 0
    for r in _active_reservations(ref_type, ref_id):
        stock = _locked_stock_by_ids(r.warehouse_id, r.variant_id)
        stock.reserved = F("reserved") - r.qty
        stock.save(update_fields=["reserved", "updated_at"])
        r.status = Reservation.Status.RELEASED
        r.save(update_fields=["status", "updated_at"])
        total += r.qty
    return total


@transaction.atomic
def commit(ref_type: str, ref_id, *, user=None) -> int:
    """Band qilingan tovar ombordan chiqdi (sotuv). on_hand va reserved kamayadi."""
    total = 0
    for r in _active_reservations(ref_type, ref_id):
        stock = _locked_stock_by_ids(r.warehouse_id, r.variant_id)
        stock.reserved = F("reserved") - r.qty
        stock.on_hand = F("on_hand") - r.qty
        stock.save(update_fields=["reserved", "on_hand", "updated_at"])
        stock.refresh_from_db()
        _movement(stock, -r.qty, StockMovement.Reason.SALE, user=user, ref=(ref_type, ref_id))
        r.status = Reservation.Status.COMMITTED
        r.save(update_fields=["status", "updated_at"])
        total += r.qty
    return total


@transaction.atomic
def return_committed(ref_type: str, ref_id, *, user=None) -> int:
    """Sotilgan (commit) tovar omborga qaytdi (eshikda rad etildi / yetkazilmadi): on_hand oshadi."""
    total = 0
    rows = list(
        Reservation.objects.select_for_update()
        .filter(ref_type=ref_type, ref_id=str(ref_id), status=Reservation.Status.COMMITTED)
        .order_by("id")
    )
    for r in rows:
        stock = _locked_stock_by_ids(r.warehouse_id, r.variant_id)
        stock.on_hand = F("on_hand") + r.qty
        stock.save(update_fields=["on_hand", "updated_at"])
        stock.refresh_from_db()
        _movement(stock, r.qty, StockMovement.Reason.RETURN, user=user, ref=(ref_type, ref_id))
        r.status = Reservation.Status.RETURNED
        r.save(update_fields=["status", "updated_at"])
        total += r.qty
    return total


def reservation_warehouses(ref_type: str, ref_id, variant_id: int) -> dict[int, int]:
    """Buyurtma bo'yicha variant qaysi omborlarda nechtadan band qilingan: {warehouse_id: qty}."""
    out: dict[int, int] = {}
    for r in Reservation.objects.filter(
        ref_type=ref_type, ref_id=str(ref_id), variant_id=variant_id, status=Reservation.Status.ACTIVE
    ):
        out[r.warehouse_id] = out.get(r.warehouse_id, 0) + r.qty
    return out


def set_serial_status(unit: SerialUnit, status: str, *, warehouse_id, ref, user=None) -> None:
    """Seriyali dona holatini o'zgartirish (tarixga yoziladi). Qator oldindan qulflangan bo'lishi kerak."""
    unit.status = status
    unit.warehouse_id = warehouse_id
    _serial_history(unit, status, ref, user)
    unit.save(update_fields=["status", "warehouse", "history", "updated_at"])


def _locked_stock_by_ids(warehouse_id: int, variant_id: int) -> Stock:
    return Stock.objects.select_for_update().get(warehouse_id=warehouse_id, variant_id=variant_id)


def release_expired(now=None) -> int:
    """Muddati o'tgan bandlarni bo'shatish (Celery beat)."""
    now = now or timezone.now()
    refs = (
        Reservation.objects.filter(status=Reservation.Status.ACTIVE, expires_at__lt=now)
        .values_list("ref_type", "ref_id")
        .distinct()
    )
    return sum(release(t, i) for t, i in refs)
