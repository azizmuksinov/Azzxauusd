"""Mijoz murojaatlari: "kelganda xabar bering" va 1 bosishda xarid (tez buyurtma)."""

from django.core.cache import cache

from apps.catalog.models import ProductVariant
from apps.core.exceptions import ApiError
from apps.core.phone import InvalidPhone, normalize_phone

from .models import QuickOrder, StockRequest

LIMIT = 6  # bitta manzildan (IP) soatiga


def _phone(raw: str) -> str:
    try:
        return normalize_phone(raw)
    except InvalidPhone as exc:
        raise ApiError(
            "invalid_phone", "Telefon raqamni to'g'ri kiriting (masalan +998 90 123 45 67)."
        ) from exc


def _rate(kind: str, ip: str) -> None:
    key = f"lead:{kind}:{ip}"
    n = cache.get(key, 0)
    if n >= LIMIT:
        raise ApiError(
            "too_many_requests", "Juda ko'p so'rov. Birozdan keyin urinib ko'ring.", status_code=429
        )
    cache.set(key, n + 1, 3600)


def _variant(variant_id) -> ProductVariant:
    v = (
        ProductVariant.objects.select_related("product")
        .filter(pk=variant_id, is_active=True, product__status="active")
        .first()
    )
    if v is None:
        raise ApiError("variant_not_found", "Tovar topilmadi.", status_code=404)
    return v


def stock_request(*, variant_id, phone: str, name: str = "", user=None, ip: str = "") -> StockRequest:
    _rate("stock", ip)
    variant, phone = _variant(variant_id), _phone(phone)
    obj = StockRequest.objects.filter(variant=variant, phone=phone, status=StockRequest.Status.NEW).first()
    if obj:
        return obj  # shu raqam bu tovarga allaqachon yozilgan
    return StockRequest.objects.create(
        variant=variant,
        phone=phone,
        name=name.strip()[:80],
        user=user if user and user.is_authenticated else None,
    )


def quick_order(
    *, variant_id, phone: str, name: str = "", qty: int = 1, comment: str = "", user=None, ip: str = ""
) -> QuickOrder:
    _rate("quick", ip)
    variant, phone = _variant(variant_id), _phone(phone)
    return QuickOrder.objects.create(
        variant=variant,
        qty=max(1, min(int(qty or 1), 99)),
        price=variant.price,
        phone=phone,
        name=name.strip()[:80],
        comment=comment.strip()[:300],
        user=user if user and user.is_authenticated else None,
    )
