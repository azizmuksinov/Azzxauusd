"""Matnli qidiruv. Filtrlar va fasetlar har doim DB'da; qidiruv backendi faqat mos tovar ID'larini
relevantlik tartibida qaytaradi. Shu sabab ikkala backend bir xil natija formatini beradi.
"""

from functools import cache

from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils.module_loading import import_string

from apps.core.i18n import LANG_KEYS, localize
from apps.core.translit import latin_to_cyrillic


class SearchBackend:
    name = "base"

    def search_ids(self, query: str, limit: int = 1000) -> list[int]:
        raise NotImplementedError

    def index_products(self, products) -> None:  # noqa: B027 - ixtiyoriy
        pass

    def delete_products(self, ids: list[int]) -> None:  # noqa: B027
        pass

    # DB backend uchun; boshqalar ID ro'yxatidan foydalanadi.
    def filter_queryset(self, qs: QuerySet, query: str) -> tuple[QuerySet, list[int] | None]:
        ids = self.search_ids(query)
        return qs.filter(pk__in=ids), ids


def normalize_query(query: str) -> list[str]:
    # ʻ ʼ ‘ ’ ` -> ' (o'zbek apostroflari turlicha yoziladi)
    for ch in "ʻʼ‘’`":
        query = query.replace(ch, "'")
    return [t for t in query.lower().split() if t][:10]


def product_document(product) -> dict:
    """Meilisearch hujjati (faqat ommaviy maydonlar; tannarx yo'q)."""
    doc = {
        "id": product.id,
        "slug": product.slug,
        "brand": product.brand.name if product.brand_id else "",
        "category_id": product.category_id,
        "model_code": product.model_code,
        "skus": list(product.variants.filter(is_active=True).values_list("sku", flat=True)),
        "status": product.status,
        "rating_count": product.rating_count,
    }
    for key in LANG_KEYS:
        doc[f"name_{key}"] = localize(product.name, key)
    if not product.name.get("uz_cyrl") and product.name.get("uz"):
        doc["name_uz_cyrl"] = latin_to_cyrillic(product.name["uz"])
    return doc


class DatabaseSearchBackend(SearchBackend):
    """PostgreSQL/SQLite: denormalizatsiyalangan `search_text` bo'yicha har bir so'z (AND)."""

    name = "db"

    def filter_queryset(self, qs, query):
        tokens = normalize_query(query)
        cond = Q()
        for t in tokens:
            cond &= Q(search_text__contains=t) | Q(search_text__contains=latin_to_cyrillic(t))
        return qs.filter(cond), None

    def search_ids(self, query, limit=1000):
        from apps.catalog.models import Product

        qs, _ = self.filter_queryset(Product.objects.all(), query)
        return list(qs.values_list("pk", flat=True)[:limit])


BACKENDS = {
    "db": "apps.catalog.search.base.DatabaseSearchBackend",
    "meilisearch": "apps.catalog.search.meili.MeilisearchBackend",
}


@cache
def _backend(name: str) -> SearchBackend:
    return import_string(BACKENDS[name])()


def get_search_backend() -> SearchBackend:
    return _backend(settings.SEARCH_BACKEND)
