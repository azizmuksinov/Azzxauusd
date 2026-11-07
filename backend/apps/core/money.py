from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value) -> Decimal:
    """So'm: 2 xonali kasr, ROUND_HALF_UP (bank yaxlitlashi emas)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
