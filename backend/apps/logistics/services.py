"""Smart routing: barcha yoqilgan provayderlardan narx so'raladi, eng arzoni (teng bo'lsa — tezi) tanlanadi.
Hozir faqat `own` provayderi bor; Fargo/BTS qo'shilganda shu funksiya o'zgarmaydi.
"""

import hashlib
import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.exceptions import ApiError
from apps.core.settings_registry import get_setting

from .models import DeliveryQuote
from .providers import ProviderError, Quote, QuoteRequest, get_providers

logger = logging.getLogger(__name__)


class DeliveryUnavailable(ApiError):
    status_code = 422
    default_code = "delivery_unavailable"
    default_detail = "Bu manzilga yetkazib berish hozircha mavjud emas."


def address_fingerprint(address) -> str:
    a = address
    raw = f"{a.pk}:{a.district_id}:{a.floor}:{a.elevator}:{a.updated_at.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def best_quote(req: QuoteRequest) -> Quote:
    quotes = []
    for provider in get_providers():
        try:
            quotes.append(provider.calculate(req))
        except ProviderError as exc:
            logger.info("%s narx bermadi: %s", provider.code, exc)
        except Exception:  # noqa: BLE001 - bitta provayder xatosi checkout'ni to'xtatmasin
            logger.exception("%s provayderida kutilmagan xato", provider.code)
    if not quotes:
        raise DeliveryUnavailable()
    return min(quotes, key=lambda q: (q.delivery_price, q.eta_days_max))


def quote_for_cart(user, address, summary) -> DeliveryQuote:
    req = QuoteRequest(
        region_id=address.district.region_id,
        district_id=address.district_id,
        weight_kg=summary.total_weight_kg,
        bulky_items=summary.bulky_items,
        floor=address.floor,
        elevator=address.elevator,
    )
    q = best_quote(req)
    return DeliveryQuote.objects.create(
        user=user,
        address=address,
        provider=q.provider,
        cart_fingerprint=summary.fingerprint,
        address_fingerprint=address_fingerprint(address),
        weight_kg=summary.total_weight_kg,
        bulky_items=summary.bulky_items,
        vehicle=q.vehicle,
        delivery_price=q.delivery_price,
        lifting_available=q.lifting_available,
        lifting_price=q.lifting_price,
        eta_days_min=q.eta_days_min,
        eta_days_max=q.eta_days_max,
        raw=q.raw,
        expires_at=timezone.now() + timedelta(minutes=get_setting("delivery_quote_ttl_minutes")),
    )


class QuoteInvalid(ApiError):
    status_code = 409
    default_code = "quote_expired"
    default_detail = "Yetkazish narxi eskirdi yoki savat/manzil o'zgardi. Narxni qayta hisoblang."


def validate_quote(public_id, user, address, summary) -> DeliveryQuote:
    quote = DeliveryQuote.objects.filter(public_id=public_id, user=user).first()
    if (
        quote is None
        or quote.used_at is not None
        or quote.expires_at <= timezone.now()
        or quote.address_id != address.pk
        or quote.address_fingerprint != address_fingerprint(address)
        or quote.cart_fingerprint != summary.fingerprint
    ):
        raise QuoteInvalid()
    return quote
