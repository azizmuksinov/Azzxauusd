"""O'z kuryerlarimiz: narx admin panelda kiritilgan zona tariflaridan olinadi."""

from decimal import Decimal

from django.db.models import Q

from apps.core.money import money
from apps.core.settings_registry import get_setting
from apps.logistics.models import DeliveryTariff, DeliveryZone

from .base import ProviderError, Quote, QuoteRequest, ShipmentResult


def find_zone(region_id: int, district_id: int) -> DeliveryZone | None:
    active = DeliveryZone.objects.filter(is_active=True)
    return (
        active.filter(districts__id=district_id).order_by("sort", "id").first()
        or active.filter(regions__id=region_id).order_by("sort", "id").first()
    )


def lifting_price(bulky_items: int, floor: int | None, elevator: str) -> Decimal | None:
    """Qavatga ko'tarish narxi; None — xizmat mavjud emas (narx sozlanmagan yoki qavat noma'lum)."""
    if bulky_items <= 0:
        return None
    if elevator in ("passenger", "freight"):
        per_item = get_setting("lifting_price_with_elevator")
        return None if per_item is None else money(per_item * bulky_items)
    per_floor = get_setting("lifting_price_per_floor")
    if per_floor is None or floor is None:
        return None
    floors = max(floor - 1, 0)  # 1-qavatga ko'tarish shart emas
    return money(per_floor * floors * bulky_items)


class ManualTariffProvider:
    code = "own"

    def calculate(self, req: QuoteRequest) -> Quote:
        zone = find_zone(req.region_id, req.district_id)
        if zone is None:
            raise ProviderError("Bu hududga yetkazish tarifi kiritilmagan")
        vehicle = DeliveryTariff.Vehicle.TRUCK if req.bulky_items else DeliveryTariff.Vehicle.STANDARD
        tariff = (
            zone.tariffs.filter(vehicle=vehicle)
            .filter(Q(max_weight_kg__isnull=True) | Q(max_weight_kg__gte=req.weight_kg))
            .order_by("max_weight_kg")  # NULL (cheklovsiz) — oxirida
            .first()
        )
        if tariff is None:
            raise ProviderError(f"{zone}: {vehicle} uchun {req.weight_kg} kg ga tarif yo'q")
        lp = lifting_price(req.bulky_items, req.floor, req.elevator)
        return Quote(
            provider=self.code,
            vehicle=vehicle,
            delivery_price=tariff.price,
            eta_days_min=zone.eta_days_min,
            eta_days_max=zone.eta_days_max,
            lifting_available=lp is not None,
            lifting_price=lp,
            raw={"zone_id": zone.id, "tariff_id": tariff.id},
        )

    # O'z kuryerimizda jo'natma tizim ichida yaratiladi (kuryer ilovasi moduli) — tashqi API yo'q.
    def create_shipment(self, shipment) -> ShipmentResult:
        return ShipmentResult(provider_shipment_id=f"own-{shipment.pk}")

    def track(self, shipment):
        return []

    def cancel(self, shipment) -> bool:
        return True
