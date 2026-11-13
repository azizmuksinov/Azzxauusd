"""Test ma'lumotlari uchun oddiy fabrikalar (tashqi kutubxonasiz)."""

import itertools
from decimal import Decimal

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeValue,
    Brand,
    Category,
    CategoryAttribute,
    Product,
    ProductVariant,
)
from apps.inventory.models import Warehouse

_seq = itertools.count(1)


def category(slug=None, parent=None, name=None, **kw):
    n = next(_seq)
    slug = slug or f"cat-{n}"
    return Category.objects.create(slug=slug, parent=parent, name=name or {"uz": f"Kategoriya {n}"}, **kw)


def brand(name="Samsung", slug=None):
    return Brand.objects.get_or_create(slug=slug or name.lower(), defaults={"name": name})[0]


def attribute(code, data_type, *, categories=(), options=(), unit="", filterable=True, **kw):
    attr = Attribute.objects.create(
        code=code,
        name=kw.pop("name", {"uz": code}),
        data_type=data_type,
        unit=unit,
        is_filterable=filterable,
        **kw,
    )
    for i, (ocode, oname) in enumerate(options):
        AttributeOption.objects.create(attribute=attr, code=ocode, value={"uz": oname}, sort=i)
    for c in categories:
        CategoryAttribute.objects.create(category=c, attribute=attr)
    return attr


def product(
    cat, *, name=None, brand_=None, price="1000000", old_price=None, status="active", variants=1, **kw
):
    n = next(_seq)
    p = Product.objects.create(
        category=cat,
        brand=brand_,
        slug=kw.pop("slug", f"product-{n}"),
        name=name or {"uz": f"Tovar {n}"},
        status=status,
        mxik_code="12345678901234567",
        serial_tracking=kw.pop("serial_tracking", Product.SerialTracking.NONE),
        **kw,
    )
    for i in range(variants):
        ProductVariant.objects.create(
            product=p,
            sku=f"SKU-{n}-{i}",
            price=Decimal(price) + i * 100000,
            old_price=Decimal(old_price) if old_price else None,
            cost_price=Decimal(price) * Decimal("0.8"),
        )
    return p


def set_attr(prod, attr, value, variant=None):
    kwargs = {"product": prod, "attribute": attr, "variant": variant}
    if attr.data_type == Attribute.DataType.ENUM:
        kwargs["option"] = attr.options.get(code=value)
    elif attr.data_type == Attribute.DataType.NUMBER:
        kwargs["value_number"] = Decimal(str(value))
    elif attr.data_type == Attribute.DataType.BOOL:
        kwargs["value_bool"] = value
    else:
        kwargs["value_text"] = {"uz": value}
    return AttributeValue.objects.create(**kwargs)


def warehouse(code="main", **kw):
    return Warehouse.objects.get_or_create(code=code, defaults={"name": kw.pop("name", code.title()), **kw})[
        0
    ]


def stock(variant, qty, wh=None):
    from apps.inventory.services import receive

    return receive(wh or warehouse(), variant, qty)


def luhn_imei(prefix: str) -> str:
    """14 xonali prefiksdan Luhn bo'yicha to'g'ri 15 xonali IMEI."""
    assert len(prefix) == 14
    for d in "0123456789":
        from apps.inventory.imei import is_valid_imei

        if is_valid_imei(prefix + d):
            return prefix + d
    raise AssertionError
