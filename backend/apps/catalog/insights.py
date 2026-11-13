"""Tovarlar holati (sotuvchi kabinetidagi kabi): qoldiq, 30 kunlik sotuv, qoldiq necha kunga yetadi,
to'ldirilmagan ma'lumotlar. Admin "Tovarlar" bo'limidagi yorliqlar (tabs) shu yerda hisoblanadi.
"""

from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from .models import Product

# Sotuv hisoblanmaydigan buyurtma holatlari (bekor, qaytgan, rad etilgan, hali tasdiqlanmagan).
NOT_SOLD = ("created", "cancelled", "returned", "refused_at_door")
LOW_STOCK = 3  # dona — "Tugayapti"
LOW_DAYS = 14  # kun — sotuv sur'atida shuncha kunga yetmasa ham "Tugayapti"

TABS = {
    "all": "Barchasi",
    "selling": "Sotuvda",
    "low": "Tugayapti",
    "out": "Tugagan",
    "not_selling": "Sotuvda emas",
    "needs_fix": "Tuzatish kerak",
    "no_dims": "O'lcham/og'irlik yo'q",
    "archived": "Arxiv",
}
FLAG_LABELS = {
    "no_image": "Rasm yo'q",
    "no_description": "Tavsif yo'q",
    "no_mxik": "MXIK kodi yo'q",
    "no_price": "Narx yo'q",
    "no_dims": "O'lcham/og'irlik yo'q",
}


def sales_30d(variant_ids) -> dict[int, int]:
    from apps.orders.models import OrderItem

    since = timezone.now() - timedelta(days=30)
    rows = (
        OrderItem.objects.filter(variant_id__in=list(variant_ids), order__created_at__gte=since)
        .exclude(order__status__in=NOT_SOLD)
        .values("variant_id")
        .annotate(n=Sum("qty"))
    )
    return {r["variant_id"]: r["n"] or 0 for r in rows}


def health(products) -> dict[int, dict]:
    """{product_id: {available, sales_30d, days_left, flags, tabs}} — ro'yxat uchun bir necha so'rovda."""
    from apps.inventory.services import available_by_variant

    products = list(products)
    vids = [v.id for p in products for v in p.variants.all()]
    avail, sold = available_by_variant(vids), sales_30d(vids)
    out = {}
    for p in products:
        variants = [v for v in p.variants.all() if v.is_active] or list(p.variants.all())
        a = sum(avail.get(v.id, 0) for v in variants)
        s = sum(sold.get(v.id, 0) for v in variants)
        days = round(a / (s / 30)) if s else None
        flags = []
        if not p.images.all():
            flags.append("no_image")
        if not (p.description or {}).get("uz"):
            flags.append("no_description")
        if not p.mxik_code:
            flags.append("no_mxik")
        if not variants or any(not v.price for v in variants):
            flags.append("no_price")
        if any(not v.weight_kg or not (v.length_cm and v.width_cm and v.height_cm) for v in variants):
            flags.append("no_dims")
        tabs = {"all"} if p.status != Product.Status.ARCHIVED else set()
        if p.status == Product.Status.ARCHIVED:
            tabs.add("archived")
        elif p.status == Product.Status.ACTIVE:
            if a <= 0:
                tabs.add("out")
            else:
                tabs.add("selling")
                if a <= LOW_STOCK or (days is not None and days < LOW_DAYS):
                    tabs.add("low")
        else:
            tabs.add("not_selling")
        if p.status != Product.Status.ARCHIVED:
            if set(flags) - {"no_dims"}:
                tabs.add("needs_fix")
            if "no_dims" in flags:
                tabs.add("no_dims")
        out[p.id] = {"available": a, "sales_30d": s, "days_left": days, "flags": flags, "tabs": sorted(tabs)}
    return out


def tab_counts(qs) -> dict[str, int]:
    counts = dict.fromkeys(TABS, 0)
    for h in health(qs).values():
        for t in h["tabs"]:
            counts[t] += 1
    return counts
