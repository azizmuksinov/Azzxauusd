"""Qaysi to'lov usullari ruxsat etilgani va qancha oldindan (onlayn) to'lash kerakligi.

Qoidalar:
- Yetkazish (va ko'tarish) narxi har doim oldindan onlayn to'lanadi (`delivery_fee_prepaid`),
  eshikda to'lovda ham.
- `cod_max_amount` dan qimmat buyurtmada: `cod_prepayment_percent` < 100 bo'lsa avans, aks holda faqat onlayn.
  Avans kamida yetkazish narxiga teng.
"""

from dataclasses import dataclass
from decimal import Decimal

from apps.core.money import money
from apps.core.settings_registry import get_setting

from .models import PaymentMethod


@dataclass(frozen=True)
class MethodOption:
    code: str
    available: bool
    required_prepayment: Decimal
    reason: str = ""


def payment_options(total: Decimal, delivery_total: Decimal = Decimal("0")) -> list[MethodOption]:
    """`delivery_total` — yetkazish + ko'tarish narxi."""
    options = [
        MethodOption(m, True, money(total))
        for m in (PaymentMethod.PAYME, PaymentMethod.CLICK, PaymentMethod.UZUM)
    ]
    cod_max = get_setting("cod_max_amount")
    percent = get_setting("cod_prepayment_percent")
    base = money(delivery_total) if get_setting("delivery_fee_prepaid") else money(0)
    note = "Yetkazish narxi oldindan onlayn to'lanadi, tovar narxi — eshik oldida" if base > 0 else ""
    # Eshikda: naqd yoki Payme/Click QR (kuryer ilovasida).
    # Kuryerlarda karta terminali yo'q — CARD_ON_DELIVERY taklif qilinmaydi.
    for m in (PaymentMethod.CASH,):
        if cod_max is None or total <= cod_max:
            options.append(MethodOption(m, True, base, note))
        elif percent < 100:
            prepay = max(base, money(total * Decimal(percent) / 100))
            options.append(
                MethodOption(m, True, prepay, f"{prepay} so'm oldindan onlayn to'lanadi, qolgani eshikda")
            )
        else:
            options.append(
                MethodOption(
                    m, False, money(total), f"{cod_max} so'mdan qimmat buyurtma faqat oldindan to'lanadi"
                )
            )
    return options


def option_for(method: str, total: Decimal, delivery_total: Decimal = Decimal("0")) -> MethodOption | None:
    return next((o for o in payment_options(total, delivery_total) if o.code == method), None)
