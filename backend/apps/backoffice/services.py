"""Back-office hujjatlarini o'tkazish (posting) va kassa hisobi."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.core.exceptions import ApiError
from apps.core.money import money
from apps.inventory import services as inventory
from apps.inventory.models import Stock

from .models import (
    CashAccount,
    CashTransaction,
    DocStatus,
    PurchaseReceipt,
    StockTransfer,
    Supplier,
    WriteOff,
)


class DocumentError(ApiError):
    status_code = 409
    default_code = "document_error"


def _lock_draft(model, doc):
    doc = model.objects.select_for_update().get(pk=doc.pk)
    if doc.status != DocStatus.DRAFT:
        raise DocumentError("not_draft", "Hujjat allaqachon o'tkazilgan yoki bekor qilingan.")
    if not doc.lines.exists():
        raise DocumentError("empty_document", "Hujjatda qatorlar yo'q.")
    return doc


def _finish(doc, user) -> None:
    doc.status = DocStatus.POSTED
    doc.posted_at = timezone.now()
    doc.posted_by = user
    doc.save(update_fields=["status", "posted_at", "posted_by", "updated_at"])


def _total_on_hand(variant_id: int) -> int:
    return Stock.objects.filter(variant_id=variant_id).aggregate(s=Coalesce(Sum("on_hand"), 0))["s"]


@transaction.atomic
def post_receipt(receipt: PurchaseReceipt, user) -> PurchaseReceipt:
    """Kirimni o'tkazish: qoldiq oshadi, seriyalar ro'yxatga olinadi, tannarx — o'rtacha og'irlikli.

    yangi_tannarx = (eski_qoldiq * eski_tannarx + kirim_soni * xarid_narxi) / (eski_qoldiq + kirim_soni)
    """
    receipt = _lock_draft(PurchaseReceipt, receipt)
    ref = ("purchase_receipt", receipt.number)
    for line in receipt.lines.select_related("variant__product"):
        variant = ProductVariant.objects.select_for_update().get(pk=line.variant_id)
        before = _total_on_hand(variant.id)
        old_cost = variant.cost_price
        if old_cost is None or before <= 0:
            new_cost = line.unit_cost
        else:
            new_cost = (Decimal(before) * old_cost + line.qty * line.unit_cost) / (before + line.qty)
        serials = [inventory.SerialInput(**s) for s in (line.serials or [])]
        inventory.receive(
            receipt.warehouse,
            variant,
            line.qty,
            serials=serials,
            user=user,
            ref=ref,
            comment=f"{receipt.supplier}",
        )
        variant.cost_price = money(new_cost)
        variant.save(update_fields=["cost_price", "updated_at"])
    _finish(receipt, user)
    return receipt


@transaction.atomic
def post_transfer(doc: StockTransfer, user) -> StockTransfer:
    doc = _lock_draft(StockTransfer, doc)
    ref = ("stock_transfer", doc.number)
    for line in doc.lines.select_related("variant__product"):
        inventory.transfer(
            doc.source,
            doc.target,
            line.variant,
            line.qty,
            serial_ids=line.serial_ids or [],
            user=user,
            ref=ref,
            comment=doc.comment,
        )
    _finish(doc, user)
    return doc


@transaction.atomic
def post_write_off(doc: WriteOff, user) -> WriteOff:
    doc = _lock_draft(WriteOff, doc)
    if doc.reason == WriteOff.Reason.RETURN_TO_SUPPLIER and not doc.supplier_id:
        raise DocumentError("supplier_required", "Ta'minotchiga qaytarishda ta'minotchini tanlang.")
    ref = ("write_off", doc.number)
    for line in doc.lines.select_related("variant__product"):
        inventory.issue(
            doc.warehouse,
            line.variant,
            line.qty,
            reason="write_off",
            serial_ids=line.serial_ids or [],
            user=user,
            ref=ref,
            comment=f"{doc.get_reason_display()}. {doc.comment}".strip(),
        )
    _finish(doc, user)
    return doc


@transaction.atomic
def cancel_draft(model, doc):
    doc = model.objects.select_for_update().get(pk=doc.pk)
    if doc.status != DocStatus.DRAFT:
        raise DocumentError(
            "not_draft",
            "Faqat qoralamani bekor qilish mumkin. O'tkazilgan hujjat uchun teskari hujjat qiling.",
        )
    doc.status = DocStatus.CANCELLED
    doc.save(update_fields=["status", "updated_at"])
    return doc


# --- kassa ---
def record_cash(
    *,
    account: CashAccount,
    direction: str,
    amount,
    category: str,
    user,
    comment: str = "",
    supplier: Supplier | None = None,
    order=None,
    occurred_at=None,
) -> CashTransaction:
    if not account.is_active:
        raise ApiError("account_inactive", "Bu hisob faol emas.")
    if category == CashTransaction.Category.SUPPLIER_PAYMENT and supplier is None:
        raise ApiError("supplier_required", "Ta'minotchiga to'lovda ta'minotchini tanlang.")
    if direction == CashTransaction.Direction.OUT and account.kind == CashAccount.Kind.CASH:
        if balance(account) < money(amount):
            raise ApiError("insufficient_cash", "Kassada yetarli naqd pul yo'q.")
    return CashTransaction.objects.create(
        account=account,
        direction=direction,
        amount=money(amount),
        category=category,
        supplier=supplier,
        order=order,
        comment=comment,
        occurred_at=occurred_at or timezone.now(),
        created_by=user,
    )


@transaction.atomic
def reverse_cash(tx: CashTransaction, user, comment: str) -> CashTransaction:
    """Xato yozuvni bekor qilish: teskari yo'nalishdagi yozuv (asl yozuv o'zgarmaydi)."""
    tx = CashTransaction.objects.select_for_update().get(pk=tx.pk)
    if tx.category == CashTransaction.Category.CORRECTION or hasattr(tx, "reversed_by"):
        raise ApiError("already_reversed", "Bu yozuv allaqachon bekor qilingan yoki o'zi tuzatish yozuvi.")
    opposite = (
        CashTransaction.Direction.OUT
        if tx.direction == CashTransaction.Direction.IN
        else CashTransaction.Direction.IN
    )
    return CashTransaction.objects.create(
        account=tx.account,
        direction=opposite,
        amount=tx.amount,
        category=CashTransaction.Category.CORRECTION,
        supplier=tx.supplier,
        order=tx.order,
        reverses=tx,
        comment=comment[:255],
        occurred_at=timezone.now(),
        created_by=user,
    )


_SIGNED = Case(
    When(direction=CashTransaction.Direction.IN, then=F("amount")),
    default=-F("amount"),
    output_field=DecimalField(max_digits=16, decimal_places=2),
)


def balance(account: CashAccount) -> Decimal:
    return money(account.transactions.aggregate(b=Coalesce(Sum(_SIGNED), Value(Decimal("0"))))["b"])


def supplier_balance(supplier: Supplier) -> dict:
    """Ta'minotchiga qarzimiz = o'tkazilgan kirimlar - to'lovlar (+ qaytarilgan to'lovlar tuzatishi)."""
    received = Decimal("0")
    for r in supplier.receipts.filter(status=DocStatus.POSTED).prefetch_related("lines"):
        received += r.total
    paid = supplier.payments.filter(
        Q(category=CashTransaction.Category.SUPPLIER_PAYMENT)
        | Q(category=CashTransaction.Category.CORRECTION)
    ).aggregate(p=Coalesce(Sum(-_SIGNED), Value(Decimal("0"))))["p"]
    return {"received": money(received), "paid": money(paid), "debt": money(received - paid)}


def stock_valuation() -> list[dict]:
    """Ombor bo'yicha qoldiq qiymati (tannarxda)."""
    rows = (
        Stock.objects.filter(on_hand__gt=0)
        .values("warehouse_id", "warehouse__name")
        .annotate(
            units=Sum("on_hand"),
            value=Coalesce(
                Sum(F("on_hand") * F("variant__cost_price")),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ),
        )
        .order_by("warehouse__name")
    )
    return [
        {
            "warehouse_id": r["warehouse_id"],
            "warehouse": r["warehouse__name"],
            "units": r["units"],
            "value": str(money(r["value"])),
        }
        for r in rows
    ]
