"""Biznes sozlamalari ro'yxati. Qiymat bazada bo'lmasa — standart qiymat ishlatiladi.

`None` standart qiymat "sozlanmagan" degani: tegishli xizmat o'chiq yoki cheklovsiz (tavsifda yozilgan).
Biznes qiymatlari (narxlar, chegaralar) taxmin qilinmaydi — admin panelda kiritiladi.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.core.cache import cache


@dataclass(frozen=True)
class SettingDef:
    default: object
    type: type
    description: str
    nullable: bool = True


REGISTRY: dict[str, SettingDef] = {
    "cart_max_qty_per_item": SettingDef(10, int, "Savatda bitta tovardan ko'pi bilan", nullable=False),
    "cod_max_amount": SettingDef(
        None, Decimal, "Eshik oldida to'lov (COD) mumkin bo'lgan maksimal summa. None — cheklovsiz (S-06)"
    ),
    "cod_prepayment_percent": SettingDef(
        100,
        int,
        "cod_max_amount dan qimmat buyurtmada avans foizi. 100 — faqat to'liq oldindan to'lov",
        nullable=False,
    ),
    "delivery_fee_prepaid": SettingDef(
        True, bool, "Yetkazish narxi eshikda to'lovda ham oldindan onlayn to'lanadi", nullable=False
    ),
    "online_payment_ttl_minutes": SettingDef(
        30,
        int,
        "Onlayn to'lov kutiladigan vaqt; o'tsa buyurtma bekor bo'ladi va tovar bo'shaydi",
        nullable=False,
    ),
    "lifting_price_per_floor": SettingDef(
        None,
        Decimal,
        "Liftsiz qavatga ko'tarish: bitta yirik tovar uchun har qavat narxi. None — xizmat yo'q",
    ),
    "lifting_price_with_elevator": SettingDef(
        None, Decimal, "Lift bilan ko'tarish: bitta yirik tovar uchun narx. None — xizmat yo'q"
    ),
    "delivery_quote_ttl_minutes": SettingDef(
        15, int, "Yetkazish narxi necha daqiqa amal qiladi", nullable=False
    ),
}

_CACHE_KEY = "core:setting:{}"


def _coerce(defn: SettingDef, value):
    if value is None:
        if not defn.nullable:
            raise ValueError("Bu sozlama bo'sh bo'lishi mumkin emas")
        return None
    if defn.type is Decimal:
        return Decimal(str(value))
    if defn.type is bool:
        if not isinstance(value, bool):
            raise ValueError("true/false kerak")
        return value
    if defn.type is int:
        if isinstance(value, bool):
            raise ValueError("Butun son kerak")
        return int(value)
    return defn.type(value)


def get_setting(key: str):
    from .models import Setting

    defn = REGISTRY[key]
    cached = cache.get(_CACHE_KEY.format(key), "__miss__")
    if cached != "__miss__":
        return _coerce(defn, cached) if cached is not None else (None if defn.nullable else defn.default)
    row = Setting.objects.filter(key=key).first()
    raw = row.value if row else defn.default
    cache.set(_CACHE_KEY.format(key), raw, 60)
    return _coerce(defn, raw) if raw is not None else None


def set_setting(key: str, value, user=None) -> None:
    from .models import Setting

    defn = REGISTRY[key]
    coerced = _coerce(defn, value)
    stored = str(coerced) if isinstance(coerced, Decimal) else coerced
    Setting.objects.update_or_create(key=key, defaults={"value": stored, "updated_by": user})
    cache.delete(_CACHE_KEY.format(key))


def all_settings() -> list[dict]:
    return [
        {
            "key": k,
            "value": _json(get_setting(k)),
            "default": _json(d.default),
            "description": d.description,
            "type": d.type.__name__.lower(),
            "nullable": d.nullable,
        }
        for k, d in REGISTRY.items()
    ]


def _json(v):
    return str(v) if isinstance(v, Decimal) else v
