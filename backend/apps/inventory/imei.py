def is_valid_imei(value: str) -> bool:
    """15 xonali IMEI, Luhn nazorat raqami bilan."""
    if not (value and len(value) == 15 and value.isdigit()):
        return False
    total = 0
    for i, ch in enumerate(value):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0
