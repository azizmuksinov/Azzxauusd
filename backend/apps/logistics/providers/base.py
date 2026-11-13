"""Yetkazish provayderi interfeysi. Implementatsiyalar: own (qo'lda tariflar) — hozir;
Fargo va BTS — keyin (API'lar ulanganda), shu interfeys bo'yicha qo'shiladi.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string


class ProviderError(Exception):
    """Provayder narx bera olmadi yoki so'rovni bajarmadi (smart routing keyingisiga o'tadi)."""


@dataclass(frozen=True)
class QuoteRequest:
    region_id: int
    district_id: int
    weight_kg: Decimal
    bulky_items: int
    floor: int | None
    elevator: str  # none | passenger | freight
    cod_amount: Decimal = Decimal("0")


@dataclass(frozen=True)
class Quote:
    provider: str
    vehicle: str
    delivery_price: Decimal
    eta_days_min: int
    eta_days_max: int
    lifting_available: bool = False
    lifting_price: Decimal | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ShipmentResult:
    provider_shipment_id: str
    tracking_number: str = ""
    label_url: str = ""


@dataclass(frozen=True)
class TrackingEvent:
    status: str
    occurred_at: datetime
    description: str = ""


class DeliveryProvider(Protocol):
    code: str

    def calculate(self, req: QuoteRequest) -> Quote: ...

    def create_shipment(self, shipment) -> ShipmentResult: ...

    def track(self, shipment) -> list[TrackingEvent]: ...

    def cancel(self, shipment) -> bool: ...


PROVIDERS = {
    "own": "apps.logistics.providers.manual.ManualTariffProvider",
}


def get_providers() -> list[DeliveryProvider]:
    return [import_string(PROVIDERS[code])() for code in settings.LOGISTICS_PROVIDERS]
