"""Ommaviy katalog so'rovlari: tovarlar ro'yxati, filtrlar, fasetlar.

Narx va qoldiq subquery bilan hisoblanadi (GROUP BY yo'q) — shuning uchun ustidan aggregate va
Exists-filtrlarni erkin qo'shish mumkin.
"""

from decimal import Decimal, InvalidOperation

from django.db.models import Count, Exists, F, IntegerField, Max, Min, OuterRef, Q, QuerySet, Subquery, Sum
from django.db.models.functions import Coalesce

from apps.core.exceptions import ApiError
from apps.inventory.models import Stock

from .models import Attribute, AttributeValue, Brand, Category, Product, ProductVariant

LOW_STOCK_THRESHOLD = 3

SORTS = {
    "popular": ["-rating_count", "-id"],
    "new": ["-created_at", "-id"],
    "price_asc": ["min_price", "id"],
    "price_desc": ["-min_price", "-id"],
    "rating": ["-rating_avg", "-rating_count", "-id"],
}


def _cheapest_variant(field: str):
    return Subquery(
        ProductVariant.objects.filter(product=OuterRef("pk"), is_active=True)
        .order_by("price", "id")
        .values(field)[:1]
    )


def _available_subquery():
    return Coalesce(
        Subquery(
            Stock.objects.filter(
                variant__product=OuterRef("pk"),
                variant__is_active=True,
                warehouse__is_active=True,
                warehouse__is_sellable=True,
            )
            .values("variant__product")
            .annotate(total=Sum(F("on_hand") - F("reserved")))
            .values("total")[:1],
            output_field=IntegerField(),
        ),
        0,
    )


def public_products() -> QuerySet[Product]:
    return (
        Product.objects.filter(status=Product.Status.ACTIVE, category__is_active=True)
        .filter(Exists(ProductVariant.objects.filter(product=OuterRef("pk"), is_active=True)))
        .annotate(
            min_price=_cheapest_variant("price"),
            min_old_price=_cheapest_variant("old_price"),
            available=_available_subquery(),
        )
        .select_related("brand", "category")
    )


def stock_status(available: int) -> str:
    if available <= 0:
        return "out_of_stock"
    if available <= LOW_STOCK_THRESHOLD:
        return "low"
    return "in_stock"


def category_attributes(category: Category | None) -> QuerySet[Attribute]:
    """Kategoriya va uning ota-kategoriyalariga biriktirilgan atributlar."""
    if category is None:
        return Attribute.objects.none()
    ids = [c.id for c in category.ancestors()]
    return Attribute.objects.filter(categoryattribute__category_id__in=ids).distinct().order_by("sort", "id")


def _parse_decimal(raw: str, name: str) -> Decimal:
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ApiError("invalid_filter", f"Filtr qiymati noto'g'ri: {name}={raw}") from exc


def parse_range(raw: str, name: str) -> tuple[Decimal | None, Decimal | None]:
    """'50..65', '50..', '..65', '55' -> (min, max)."""
    if ".." in raw:
        lo, hi = raw.split("..", 1)
        return (_parse_decimal(lo, name) if lo else None, _parse_decimal(hi, name) if hi else None)
    v = _parse_decimal(raw, name)
    return v, v


def attribute_filters(params) -> dict[str, str]:
    """Query string'dan `f[code]=value` filtrlarini ajratadi."""
    out = {}
    for key in params:
        if key.startswith("f[") and key.endswith("]"):
            out[key[2:-1]] = params.get(key)
    return out


def _attr_condition(attribute: Attribute, raw: str) -> Q:
    values = AttributeValue.objects.filter(product=OuterRef("pk"), attribute=attribute)
    if attribute.data_type == Attribute.DataType.ENUM:
        codes = [c for c in raw.split(",") if c]
        values = values.filter(option__code__in=codes)
    elif attribute.data_type == Attribute.DataType.NUMBER:
        lo, hi = parse_range(raw, attribute.code)
        if lo is not None:
            values = values.filter(value_number__gte=lo)
        if hi is not None:
            values = values.filter(value_number__lte=hi)
    elif attribute.data_type == Attribute.DataType.BOOL:
        values = values.filter(value_bool=raw.lower() in ("1", "true", "ha", "yes"))
    else:
        raise ApiError("invalid_filter", f"Bu xususiyat bo'yicha filtrlab bo'lmaydi: {attribute.code}")
    return Q(Exists(values))


def apply_filters(qs: QuerySet[Product], params, *, category: Category | None = None) -> QuerySet[Product]:
    if category is not None:
        qs = qs.filter(category_id__in=category.descendant_ids())

    if brands := params.get("brand"):
        qs = qs.filter(brand__slug__in=[b for b in brands.split(",") if b])

    if raw := params.get("price_min"):
        qs = qs.filter(min_price__gte=_parse_decimal(raw, "price_min"))
    if raw := params.get("price_max"):
        qs = qs.filter(min_price__lte=_parse_decimal(raw, "price_max"))

    if params.get("in_stock") in ("1", "true"):
        qs = qs.filter(available__gt=0)
    if params.get("bulky") in ("0", "false"):
        qs = qs.filter(is_bulky=False)

    filters = attribute_filters(params)
    if filters:
        attrs = {a.code: a for a in Attribute.objects.filter(code__in=filters.keys(), is_filterable=True)}
        unknown = set(filters) - set(attrs)
        if unknown:
            raise ApiError("invalid_filter", f"Noma'lum filtr: {', '.join(sorted(unknown))}")
        for code, raw in filters.items():
            qs = qs.filter(_attr_condition(attrs[code], raw))
    return qs


def apply_sort(qs: QuerySet[Product], sort: str | None) -> QuerySet[Product]:
    if sort and sort not in SORTS:
        raise ApiError("invalid_sort", f"Saralash noto'g'ri. Mumkin: {', '.join(SORTS)}")
    return qs.order_by(*SORTS[sort or "popular"])


def _str(value) -> str | None:
    """Pul va o'lchovlar API'da satr ko'rinishida (float yaxlitlash xatolarisiz)."""
    return None if value is None else str(value)


def facets(qs: QuerySet[Product], category: Category | None, lang: str) -> dict:
    """Joriy filtrlar ostidagi fasetlar: brendlar, narx oralig'i, kategoriya atributlari."""
    from apps.core.i18n import localize

    ids = qs.values("pk")
    brands = (
        Brand.objects.filter(products__in=ids)
        .annotate(count=Count("products", distinct=True))
        .order_by("-count", "name")
        .values("slug", "name", "count")
    )
    price = {k: _str(v) for k, v in qs.aggregate(min=Min("min_price"), max=Max("min_price")).items()}

    attrs = []
    for attr in category_attributes(category).filter(is_filterable=True):
        values = AttributeValue.objects.filter(product__in=ids, attribute=attr)
        item = {
            "code": attr.code,
            "name": localize(attr.name, lang),
            "type": attr.data_type,
            "unit": attr.unit,
        }
        if attr.data_type == Attribute.DataType.ENUM:
            rows = (
                values.filter(option__isnull=False)
                .values("option__code", "option__value", "option__sort")
                .annotate(count=Count("product", distinct=True))
                .order_by("option__sort", "option__code")
            )
            item["options"] = [
                {"code": r["option__code"], "name": localize(r["option__value"], lang), "count": r["count"]}
                for r in rows
            ]
            if not item["options"]:
                continue
        elif attr.data_type == Attribute.DataType.NUMBER:
            agg = values.aggregate(min=Min("value_number"), max=Max("value_number"))
            if agg["min"] is None:
                continue
            item.update(min=_str(agg["min"]), max=_str(agg["max"]))
        elif attr.data_type == Attribute.DataType.BOOL:
            count = values.filter(value_bool=True).values("product").distinct().count()
            if not count:
                continue
            item["count_true"] = count
        else:
            continue
        attrs.append(item)

    return {"brands": list(brands), "price": price, "attributes": attrs}
