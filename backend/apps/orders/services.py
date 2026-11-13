from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Address
from apps.cart.services import CartSummary, summarize
from apps.core.exceptions import ApiError
from apps.core.settings_registry import get_setting
from apps.inventory import services as inventory
from apps.logistics.models import DeliveryQuote
from apps.logistics.services import QuoteInvalid, validate_quote

from .models import Order, OrderItem, OrderStatus, OrderStatusHistory, PaymentMethod
from .payment_rules import option_for
from .state import CUSTOMER_CANCELLABLE, transition


def _address_snapshot(a: Address) -> dict:
    return {
        "address_id": a.pk,
        "region_id": a.district.region_id,
        "district_id": a.district_id,
        "district": a.district.name,
        "settlement": a.settlement,
        "street": a.street,
        "house": a.house,
        "apartment": a.apartment,
        "entrance": a.entrance,
        "floor": a.floor,
        "elevator": a.elevator,
        "intercom": a.intercom,
        "landmark": a.landmark,
        "latitude": str(a.latitude) if a.latitude is not None else None,
        "longitude": str(a.longitude) if a.longitude is not None else None,
    }


def checkout_totals(summary: CartSummary, quote, lifting: bool, promo_code: str = "", user=None) -> dict:
    if lifting and not quote.lifting_available:
        raise ApiError("lifting_unavailable", "Bu buyurtma uchun qavatga ko'tarish xizmati mavjud emas.")
    lifting_fee = quote.lifting_price if lifting else Decimal("0")
    discount, code = Decimal("0"), ""
    if (promo_code or "").strip():
        # Promokod faqat tovarlar summasiga chegirma beradi; yaroqsiz bo'lsa — sababi bilan xato.
        from apps.marketing import promo

        found, discount = promo.validate(promo_code, summary.subtotal, user)
        code = found.code
    total = summary.subtotal - discount + quote.delivery_price + lifting_fee
    return {
        "subtotal": summary.subtotal,
        "delivery_fee": quote.delivery_price,
        "lifting_fee": lifting_fee,
        "discount_total": discount,
        "promo_code": code,
        "total": total,
    }


def _ensure_cart_ok(summary: CartSummary) -> None:
    if not summary.lines:
        raise ApiError("cart_empty", "Savat bo'sh.")
    problems = [
        {
            "variant_id": line.variant.id,
            "sku": line.variant.sku,
            "problem": line.problem,
            "available": line.available,
        }
        for line in summary.lines
        if line.problem
    ]
    if problems:
        raise ApiError(
            "cart_has_problems",
            "Savatdagi ba'zi tovarlar mavjud emas.",
            status_code=409,
            extra={"items": problems},
        )


def place_order(
    *,
    user,
    cart,
    address: Address,
    quote_id,
    payment_method: str,
    lifting: bool,
    comment: str,
    idempotency_key: str,
    language: str,
    promo_code: str = "",
) -> tuple[Order, bool]:
    """Buyurtma yaratadi. Qaytaradi: (order, created).

    Bir xil Idempotency-Key bilan qayta chaqirilsa — o'sha buyurtma qaytadi.
    """
    existing = Order.objects.filter(user=user, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False

    summary = summarize(cart)
    _ensure_cart_ok(summary)
    quote = validate_quote(quote_id, user, address, summary)
    totals = checkout_totals(summary, quote, lifting, promo_code, user)

    option = option_for(payment_method, totals["total"], totals["delivery_fee"] + totals["lifting_fee"])
    if option is None or not option.available:
        raise ApiError("payment_method_unavailable", option.reason if option else "To'lov usuli noto'g'ri.")

    online = payment_method in PaymentMethod.online()
    deadline = timezone.now() + timedelta(minutes=get_setting("online_payment_ttl_minutes"))
    needs_online_payment = online or option.required_prepayment > 0

    try:
        with transaction.atomic():
            # Parallel ikkinchi buyurtma bo'lmasligi uchun quote qulflanadi va qayta tekshiriladi.
            locked = DeliveryQuote.objects.select_for_update().get(pk=quote.pk)
            if locked.used_at is not None:
                raise QuoteInvalid()
            order = Order.objects.create(
                user=user,
                payment_method=payment_method,
                **totals,
                required_prepayment=option.required_prepayment,
                cod_amount=Decimal("0") if online else totals["total"] - option.required_prepayment,
                address_snapshot=_address_snapshot(address),
                recipient_name=address.recipient_name,
                recipient_phone=address.recipient_phone,
                lifting_requested=lifting,
                delivery_provider=quote.provider,
                delivery_vehicle=quote.vehicle,
                delivery_eta_min=quote.eta_days_min,
                delivery_eta_max=quote.eta_days_max,
                delivery_quote=quote,
                customer_comment=comment,
                language=language,
                idempotency_key=idempotency_key,
                payment_deadline=deadline if needs_online_payment else None,
            )
            order.number = f"{timezone.localdate():%y}-{order.pk:07d}"
            order.save(update_fields=["number"])
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        variant=line.variant,
                        product_name=line.variant.product.name,
                        variant_name=line.variant.name_suffix,
                        sku=line.variant.sku,
                        qty=line.item.qty,
                        unit_price=line.unit_price,
                        line_total=line.line_total,
                        cost_price=line.variant.cost_price,
                        warranty_months=line.variant.product.warranty_months,
                        mxik_code=line.variant.product.mxik_code,
                        vat_percent=line.variant.product.vat_percent,
                        is_bulky=line.variant.product.is_bulky,
                    )
                    for line in summary.lines
                ]
            )
            inventory.reserve(
                "order",
                order.pk,
                [(line.variant, line.item.qty) for line in summary.lines],
                # Onlayn to'lov kutilsa — zaxira chegara; asosiy bekor qilish cancel_unpaid_orders'da.
                expires_at=deadline + timedelta(minutes=5) if needs_online_payment else None,
            )
            OrderStatusHistory.objects.create(
                order=order,
                to_status=OrderStatus.CREATED,
                actor_type=OrderStatusHistory.Actor.CUSTOMER,
                actor=user,
            )
            quote.used_at = timezone.now()
            quote.save(update_fields=["used_at"])
            cart.items.all().delete()
    except IntegrityError:
        # Parallel so'rov xuddi shu Idempotency-Key bilan buyurtmani yaratib ulgurdi.
        existing = Order.objects.filter(user=user, idempotency_key=idempotency_key).first()
        if existing:
            return existing, False
        raise
    return order, True


def cancel_by_customer(order: Order, reason: str) -> Order:
    if order.status not in CUSTOMER_CANCELLABLE:
        raise ApiError(
            "cannot_cancel",
            "Buyurtma qadoqlangan — bekor qilish uchun operatorga murojaat qiling.",
            status_code=409,
        )
    order.cancel_reason = reason[:255]
    order.save(update_fields=["cancel_reason", "updated_at"])
    return transition(order, OrderStatus.CANCELLED, actor_type="customer", actor=order.user, note=reason)


def cancel_unpaid_orders(now=None) -> int:
    """To'lov muddati o'tgan, hali to'lanmagan buyurtmalarni bekor qiladi (celery-beat)."""
    now = now or timezone.now()
    count = 0
    pending = Q(payments__status="pending")  # provayderda jarayondagi to'lov bor — kutamiz
    expired = Order.objects.filter(status=OrderStatus.CREATED, payment_deadline__lt=now, paid_amount=0)
    for order in expired.exclude(pending).distinct():
        transition(order, OrderStatus.CANCELLED, actor_type="system", note="To'lov muddati o'tdi")
        Order.objects.filter(pk=order.pk).update(cancel_reason="payment_timeout")
        count += 1
    return count
