"""Meilisearch backendi (REST API, httpx). Bitta indeks, har til uchun alohida maydon.

Indeks sozlamalari `ensure_index()` bilan o'rnatiladi (deploy'da: manage.py search_reindex).
"""

import logging

import httpx
from django.conf import settings

from .base import SearchBackend, product_document

logger = logging.getLogger(__name__)

SEARCHABLE = ["name_uz", "name_uz_cyrl", "name_ru", "brand", "model_code", "skus"]


class MeilisearchBackend(SearchBackend):
    name = "meilisearch"

    def __init__(self, client: httpx.Client | None = None):
        cfg = settings.MEILISEARCH
        self.index = cfg["INDEX"]
        headers = {"Authorization": f"Bearer {cfg['API_KEY']}"} if cfg["API_KEY"] else {}
        self.client = client or httpx.Client(base_url=cfg["URL"], headers=headers, timeout=cfg["TIMEOUT"])

    def ensure_index(self) -> None:
        self.client.post("/indexes", json={"uid": self.index, "primaryKey": "id"})  # bor bo'lsa — 409 task
        self.client.patch(
            f"/indexes/{self.index}/settings",
            json={
                "searchableAttributes": SEARCHABLE,
                "filterableAttributes": ["category_id", "status", "brand"],
                "sortableAttributes": ["rating_count"],
                "typoTolerance": {"enabled": True},
            },
        ).raise_for_status()

    def search_ids(self, query, limit=1000):
        try:
            resp = self.client.post(
                f"/indexes/{self.index}/search",
                json={
                    "q": query,
                    "limit": limit,
                    "attributesToRetrieve": ["id"],
                    "filter": "status = active",
                },
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            # Meilisearch ishlamasa — DB qidiruviga tushamiz (sayt qidiruvsiz qolmasin).
            logger.exception("Meilisearch ishlamadi, DB qidiruviga o'tildi")
            from .base import DatabaseSearchBackend

            return DatabaseSearchBackend().search_ids(query, limit)
        return [hit["id"] for hit in resp.json().get("hits", [])]

    def index_products(self, products) -> None:
        docs = [product_document(p) for p in products]
        if docs:
            self.client.post(f"/indexes/{self.index}/documents", json=docs).raise_for_status()

    def delete_products(self, ids) -> None:
        if ids:
            self.client.post(
                f"/indexes/{self.index}/documents/delete-batch", json=list(ids)
            ).raise_for_status()
