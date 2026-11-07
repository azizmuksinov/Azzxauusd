"""Savat bilan ishlash. Narxlar savatda saqlanmaydi — har doim joriy narx olinadi."""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product, ProductVariant
from apps.core.exceptions import ApiError
from apps.core.settings_registry import get_setting
from apps.inventory.services import available_by_variant

from .models import Cart, CartItem

GUEST_HEADER = "HTTP_X_CART_TOKEN"


class NotEnoughStock(ApiError):
    status_code = 409
    default_code = "not_enough_stock"
    default_detail = "Omborda shuncha tovar yo'q."


def _guest_token(request) -> uuid.UUID | None:
    raw = request.META.get(GUEST_HEADER)
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ApiError("invalid_cart_token", "X-Cart-Token noto'g'ri.") from exc


def get_cart(request, *, create: bool = False) -> Cart | None:
    user = request.user if request.user.is_authenticated else None
    if user:
        cart = Cart.objects.filter(user=user).first()
        if cart is None and create:
            cart, _ = Cart.objects.get_or_create(user=user)
        return cart
    token = _guest_token(request)
    if token:
        cart = Cart.objects.filter(guest_token=token, user__isnull=True).first()
        if cart:
            return cart
    return Cart.objects.create() if create else None


def sellable_variant(variant_id: int) -> ProductVariant:
    variant = (
        ProductVariant.objects.select_related("product")
        .filter(pk=variant_id, is_active=True, product__status=Product.Status.ACTIVE)
        .first()
    )
    if variant is None:
        raise ApiError("variant_unavailable", "Bu tovar sotuvda yo'q.", status_code=404)
    return variant


def _check_qty(variant: ProductVariant, qty: int) -> None:
    limit = get_setting("cart_max_qty_per_item")
    if qty > limit:
        raise ApiError("qty_limit", f"Bitta tovardan ko'pi bilan {limit} dona.", extra={"max_qty": limit})
    available = available_by_variant([variant.id]).get(variant.id, 0)
    if qty > available:
        raise NotEnoughStock(extra={"available": available})


@transaction.atomic
def add_item(cart: Cart, variant_id: int, qty: int) -> CartItem:
    variant = sellable_variant(variant_id)
    item = CartItem.objects.select_for_update().filter(cart=cart, variant=variant).first()
    new_qty = (item.qty if item else 0) + qty
    _check_qty(variant, new_qty)
    if item:
        item.qty = new_qty
        item.save(update_fields=["qty"])
    else:
        item = CartItem.objects.create(cart=cart, variant=variant, qty=new_qty)
    cart.save(update_fields=["updated_at"])
    return item


def set_qty(item: CartItem, qty: int) -> CartItem:
    _check_qty(sellable_variant(item.variant_id), qty)
    item.qty = qty
    item.save(update_fields=["qty"])
    return item


@transaction.atomic
def merge(guest: Cart, target: Cart) -> Cart:
    """Login'dan keyin mehmon savati foydalanuvchi savatiga qo'shiladi (limit va qoldiq hisobga olinadi)."""
    if guest.pk == target.pk:
        return target
    limit = get_setting("cart_max_qty_per_item")
    items = list(guest.items.all())
    avail = available_by_variant(i.variant_id for i in items)
    for gi in items:
        ti = CartItem.objects.filter(cart=target, variant_id=gi.variant_id).first()
        qty = min(gi.qty + (ti.qty if ti else 0), limit)
        if avail.get(gi.variant_id, 0) > 0:
            qty = min(
                qty, avail[gi.variant_id]
            )  # qoldiq bo'lmasa — miqdor qoladi, savatda "muammo" sifatida chiqadi
        if ti:
            ti.qty = qty
            ti.save(update_fields=["qty"])
        else:
            CartItem.objects.create(cart=target, variant_id=gi.variant_id, qty=qty)
    guest.delete()
    return target


@dataclass
class CartLine:
    item: CartItem
    variant: ProductVariant
    unit_price: Decimal
    line_total: Decimal
    available: int
    problem: str | None  # unavailable | not_enough_stock | None


@dataclass
class CartSummary:
    cart: Cart | None
    lines: list[CartLine] = field(default_factory=list)
    subtotal: Decimal = Decimal("0")
    items_count: int = 0
    total_weight_kg: Decimal = Decimal("0")
    bulky_items: int = 0

    @property
    def has_problems(self) -> bool:
        return any(line.problem for line in self.lines)

    @property
    def fingerprint(self) -> str:
        """Savat tarkibining izi: yetkazish narxi qaysi savat uchun hisoblanganini tekshirish uchun."""
        raw = ",".join(
            f"{line.variant.id}:{line.item.qty}" for line in sorted(self.lines, key=lambda x: x.variant.id)
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


def summarize(cart: Cart | None) -> CartSummary:
    summary = CartSummary(cart=cart)
    if cart is None:
        return summary
    items = list(
        cart.items.select_related("variant__product__brand", "variant__product__category").order_by(
            "created_at", "id"
        )
    )
    avail = available_by_variant(i.variant_id for i in items)
    for item in items:
        v = item.variant
        problem = None
        if not v.is_active or v.product.status != Product.Status.ACTIVE:
            problem = "unavailable"
        elif item.qty > avail.get(v.id, 0):
            problem = "not_enough_stock"
        line_total = v.price * item.qty
        summary.lines.append(CartLine(item, v, v.price, line_total, avail.get(v.id, 0), problem))
        if problem != "unavailable":
            summary.subtotal += line_total
            summary.items_count += item.qty
            summary.total_weight_kg += v.weight_kg * item.qty
            if v.product.is_bulky:
                summary.bulky_items += item.qty
    return summary


def cleanup_guest_carts(days: int = 30) -> int:
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = Cart.objects.filter(user__isnull=True, updated_at__lt=cutoff).delete()
    return deleted
