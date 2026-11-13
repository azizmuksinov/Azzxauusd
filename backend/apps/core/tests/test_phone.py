import pytest

from apps.core.phone import InvalidPhone, mask_phone, normalize_phone


@pytest.mark.parametrize(
    "raw",
    ["+998901234567", "998901234567", "901234567", "+998 (90) 123-45-67", "8 90 123 45 67"],
)
def test_normalize_valid(raw):
    assert normalize_phone(raw) == "+998901234567"


@pytest.mark.parametrize("raw", ["", "12345", "+7 912 345 67 89", "+998 01 234 56 78", "abc"])
def test_normalize_invalid(raw):
    with pytest.raises(InvalidPhone):
        normalize_phone(raw)


def test_mask():
    assert mask_phone("+998901234567") == "+998 90 ***-**-67"
