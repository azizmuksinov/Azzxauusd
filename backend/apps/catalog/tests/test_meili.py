import json

import httpx
import pytest

from apps.catalog.search.meili import MeilisearchBackend
from apps.catalog.tests import factories as f

pytestmark = pytest.mark.django_db


def backend(handler):
    return MeilisearchBackend(
        client=httpx.Client(base_url="http://meili.test", transport=httpx.MockTransport(handler))
    )


def test_index_documents_have_no_cost_price():
    p = f.product(f.category(), name={"uz": "Muzlatkich Artel"}, brand_=f.brand("Artel"))
    sent = {}

    def handler(req):
        sent["path"] = req.url.path
        sent["docs"] = json.loads(req.content)
        return httpx.Response(202, json={"taskUid": 1})

    backend(handler).index_products([p])
    assert sent["path"] == "/indexes/products/documents"
    doc = sent["docs"][0]
    assert doc["name_uz"] == "Muzlatkich Artel" and doc["name_uz_cyrl"] == "Музлаткич Артел"
    assert doc["brand"] == "Artel" and "cost_price" not in json.dumps(doc)


def test_search_ids():
    def handler(req):
        body = json.loads(req.content)
        assert body["q"] == "muzlatkch" and body["filter"] == "status = active"
        return httpx.Response(200, json={"hits": [{"id": 3}, {"id": 1}]})

    assert backend(handler).search_ids("muzlatkch") == [3, 1]


def test_search_falls_back_to_db_when_down():
    p = f.product(f.category(), name={"uz": "Konditsioner"})

    def handler(req):
        raise httpx.ConnectError("down")

    assert backend(handler).search_ids("konditsioner") == [p.id]


def test_relevance_order_in_api(api_client, settings, monkeypatch):
    settings.SEARCH_BACKEND = "meilisearch"
    cat = f.category()
    a = f.product(cat, name={"uz": "A"})
    b = f.product(cat, name={"uz": "B"})
    monkeypatch.setattr(MeilisearchBackend, "search_ids", lambda self, q, limit=1000: [b.id, a.id])
    monkeypatch.setattr(MeilisearchBackend, "__init__", lambda self, client=None: None)
    from apps.catalog.search import base

    base._backend.cache_clear()
    try:
        resp = api_client.get("/api/v1/search", {"q": "har qanday"})
        assert [p["id"] for p in resp.json()["results"]] == [b.id, a.id]
    finally:
        base._backend.cache_clear()
