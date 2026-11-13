"""O'zbekiston telefon raqamlarini yagona formatga keltirish: +998XXXXXXXXX."""

import re

_DIGITS = re.compile(r"\D+")


class InvalidPhone(ValueError):
    pass


def normalize_phone(raw: str) -> str:
    """'+998 90 123-45-67', '998901234567', '901234567', '8 90 1234567' -> '+998901234567'."""
    if not raw:
        raise InvalidPhone("Telefon raqam bo'sh")
    digits = _DIGITS.sub("", str(raw))
    if len(digits) == 12 and digits.startswith("998"):
        local = digits[3:]
    elif len(digits) == 9:
        local = digits
    elif len(digits) == 10 and digits.startswith("8"):  # eski format: 8 90 1234567
        local = digits[1:]
    else:
        raise InvalidPhone("Telefon raqam formati noto'g'ri")
    if local[0] == "0":
        raise InvalidPhone("Telefon raqam formati noto'g'ri")
    return f"+998{local}"


def mask_phone(phone: str) -> str:
    """+998901234567 -> +998 90 ***-**-67 (loglar va kuryer ekrani uchun)."""
    return f"{phone[:4]} {phone[4:6]} ***-**-{phone[-2:]}"
