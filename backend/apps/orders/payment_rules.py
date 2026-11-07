"""Qaysi to'lov usullari ruxsat etilgani va qancha oldindan to'lov kerakligi (S-06 sozlamalari bilan)."""

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


def payment_options(total: Decimal) -> list[MethodOption]:
    options = [
        MethodOption(m, True, total) for m in (PaymentMethod.PAYME, PaymentMethod.CLICK, PaymentMethod.UZUM)
    ]
    cod_max = get_setting("cod_max_amount")
    percent = get_setting("cod_prepayment_percent")
    for m in (PaymentMethod.CASH, PaymentMethod.CARD_ON_DELIVERY):
        if cod_max is None or total <= cod_max:
            options.append(MethodOption(m, True, money(0)))
        elif percent < 100:
            prepay = money(total * Decimal(percent) / 100)
            options.append(
                MethodOption(m, True, prepay, f"{percent}% avans onlayn to'lanadi, qolgani eshikda")
            )
        else:
            options.append(
                MethodOption(m, False, total, f"{cod_max} so'mdan qimmat buyurtma faqat oldindan to'lanadi")
            )
    return options


def option_for(method: str, total: Decimal) -> MethodOption | None:
    return next((o for o in payment_options(total) if o.code == method), None)
