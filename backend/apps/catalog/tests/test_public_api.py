import pytest
from django.urls import reverse

from apps.catalog.models import Attribute, Product
from apps.catalog.tests import factories as f

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalog():
    """Elektronika > Televizorlar, 3 ta TV (2 brend), 1 ta qoralama, xususiyatlar va qoldiq bilan."""
    root = f.category("elektronika", name={"uz": "Elektronika", "ru": "Электроника"})
    tv = f.category("televizorlar", parent=root, name={"uz": "Televizorlar", "ru": "Телевизоры"})
    samsung, lg = f.brand("Samsung"), f.brand("LG")
    size = f.attribute(
        "screen_size",
        Attribute.DataType.NUMBER,
        categories=[root],
        unit="dyuym",
        name={"uz": "Ekran diagonali", "ru": "Диагональ"},
        group_name={"uz": "Ekran"},
    )
    smart = f.attribute("smart_tv", Attribute.DataType.BOOL, categories=[tv])
    color = f.attribute(
        "color", Attribute.DataType.ENUM, categories=[tv], options=[("black", "Qora"), ("white", "Oq")]
    )

    a = f.product(
        tv,
        name={"uz": "Samsung QLED televizor", "ru": "Телевизор Samsung QLED"},
        brand_=samsung,
        price="9000000",
        old_price="10000000",
        slug="samsung-qled",
    )
    b = f.product(tv, name={"uz": "LG OLED televizor"}, brand_=lg, price="15000000", slug="lg-oled")
    c = f.product(tv, name={"uz": "Samsung Crystal"}, brand_=samsung, price="5000000", slug="samsung-crystal")
    f.product(tv, name={"uz": "Yashirin"}, brand_=samsung, status="draft", slug="draft-one")

    for p, s, sm, col in [(a, 55, True, "black"), (b, 65, True, "white"), (c, 43, False, "black")]:
        f.set_attr(p, size, s)
        f.set_attr(p, smart, sm)
        f.set_attr(p, color, col)
    f.stock(a.variants.first(), 10)
    f.stock(b.variants.first(), 2)
    return {"root": root, "tv": tv, "a": a, "b": b, "c": c}


def slugs(resp):
    assert resp.status_code == 200, resp.json()
    return [p["slug"] for p in resp.json()["results"]]


def test_list_hides_drafts_and_cost_price(api_client, catalog):
    resp = api_client.get(reverse("product-list"))
    assert set(slugs(resp)) == {"samsung-qled", "lg-oled", "samsung-crystal"}
    assert "cost_price" not in str(resp.json())


def test_product_without_active_variant_hidden(api_client, catalog):
    catalog["c"].variants.update(is_active=False)
    assert "samsung-crystal" not in slugs(api_client.get(reverse("product-list")))


def test_card_fields(api_client, catalog):
    resp = api_client.get(reverse("product-list"), {"sort": "price_asc"})
    cards = {p["slug"]: p for p in resp.json()["results"]}
    qled = cards["samsung-qled"]
    assert qled["price"] == "9000000.00" and qled["old_price"] == "10000000.00"
    assert qled["discount_percent"] == 10
    assert qled["stock_status"] == "in_stock"
    assert cards["lg-oled"]["stock_status"] == "low"
    assert cards["samsung-crystal"]["stock_status"] == "out_of_stock"
    assert resp.json()["count"] == 3


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        (
            {"category": "elektronika"},
            {"samsung-qled", "lg-oled", "samsung-crystal"},
        ),  # ichki kategoriyalar bilan
        ({"brand": "lg"}, {"lg-oled"}),
        ({"brand": "lg,samsung"}, {"samsung-qled", "lg-oled", "samsung-crystal"}),
        ({"price_min": "6000000", "price_max": "10000000"}, {"samsung-qled"}),
        ({"in_stock": "true"}, {"samsung-qled", "lg-oled"}),
        ({"f[screen_size]": "50..65"}, {"samsung-qled", "lg-oled"}),
        ({"f[screen_size]": "..50"}, {"samsung-crystal"}),
        ({"f[smart_tv]": "true"}, {"samsung-qled", "lg-oled"}),
        ({"f[color]": "black"}, {"samsung-qled", "samsung-crystal"}),
        ({"f[color]": "black", "brand": "samsung", "f[smart_tv]": "true"}, {"samsung-qled"}),
    ],
)
def test_filters(api_client, catalog, params, expected):
    assert set(slugs(api_client.get(reverse("product-list"), params))) == expected


def test_sorting(api_client, catalog):
    assert slugs(api_client.get(reverse("product-list"), {"sort": "price_asc"})) == [
        "samsung-crystal",
        "samsung-qled",
        "lg-oled",
    ]
    assert slugs(api_client.get(reverse("product-list"), {"sort": "price_desc"}))[0] == "lg-oled"


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"f[unknown]": "1"}, "invalid_filter"),
        ({"sort": "cheap"}, "invalid_sort"),
        ({"price_min": "abc"}, "invalid_filter"),
        ({"f[screen_size]": "x..y"}, "invalid_filter"),
    ],
)
def test_bad_params(api_client, catalog, params, code):
    resp = api_client.get(reverse("product-list"), params)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == code


def test_unknown_category_404(api_client, catalog):
    assert api_client.get(reverse("product-list"), {"category": "yoq"}).status_code == 404


def test_facets(api_client, catalog):
    resp = api_client.get(reverse("category-filters", args=["televizorlar"]))
    assert resp.status_code == 200
    data = resp.json()
    assert {b["slug"]: b["count"] for b in data["brands"]} == {"samsung": 2, "lg": 1}
    assert data["price"] == {"min": "5000000.00", "max": "15000000.00"}
    attrs = {a["code"]: a for a in data["attributes"]}
    assert attrs["screen_size"]["min"] == "43.000" and attrs["screen_size"]["max"] == "65.000"
    assert attrs["smart_tv"]["count_true"] == 2
    assert {o["code"]: o["count"] for o in attrs["color"]["options"]} == {"black": 2, "white": 1}

    # fasetlar joriy filtrlar ostida hisoblanadi
    data = api_client.get(reverse("category-filters", args=["televizorlar"]), {"brand": "samsung"}).json()
    assert {
        o["code"]: o["count"] for o in {a["code"]: a for a in data["attributes"]}["color"]["options"]
    } == {"black": 2}


def test_category_tree_and_detail(api_client, catalog):
    tree = api_client.get(reverse("category-tree"), HTTP_ACCEPT_LANGUAGE="ru").json()
    assert tree[0]["name"] == "Электроника"
    assert tree[0]["children"][0]["slug"] == "televizorlar"
    detail = api_client.get(reverse("category-detail", args=["televizorlar"])).json()
    assert [c["slug"] for c in detail["breadcrumbs"]] == ["elektronika", "televizorlar"]


def test_product_detail(api_client, catalog):
    resp = api_client.get(reverse("product-detail", args=["samsung-qled"]), HTTP_ACCEPT_LANGUAGE="ru")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Телевизор Samsung QLED"
    assert data["variants"][0]["stock_status"] == "in_stock"
    assert "cost_price" not in data["variants"][0]
    groups = {g["group"]: g["items"] for g in data["attributes"]}
    assert {"code": "screen_size", "name": "Диагональ", "value": "55 dyuym"} in groups["Ekran"]
    assert [c["slug"] for c in data["category"]] == ["elektronika", "televizorlar"]


def test_product_detail_cyrillic_autotranslit(api_client, catalog):
    data = api_client.get(reverse("product-detail", args=["lg-oled"]), {"lang": "uz_cyrl"}).json()
    assert data["name"] == "ЛГ ОЛЕД телевизор"


def test_draft_detail_404(api_client, catalog):
    assert api_client.get(reverse("product-detail", args=["draft-one"])).status_code == 404


def test_variant_options(api_client, catalog):
    p = catalog["a"]
    memory = f.attribute("memory", Attribute.DataType.ENUM, options=[("128", "128 GB")])
    v = p.variants.first()
    f.set_attr(p, memory, "128", variant=v)
    data = api_client.get(reverse("product-detail", args=[p.slug])).json()
    assert data["variants"][0]["options"]["memory"]["value"] == "128 GB"


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("samsung", {"samsung-qled", "samsung-crystal"}),
        ("SAMSUNG qled", {"samsung-qled"}),
        # kategoriya nomi ham qidiriladi: "Samsung Crystal" nomida "televizor" yo'q, lekin u televizor
        ("телевизор", {"samsung-qled", "lg-oled", "samsung-crystal"}),  # ruscha + lotindan kirill
        ("televizor", {"samsung-qled", "lg-oled", "samsung-crystal"}),
        ("oled", {"lg-oled"}),
        ("Самсунг", {"samsung-qled", "samsung-crystal"}),  # kirillda yozilgan brend (translit)
        ("yoqtovar", set()),
    ],
)
def test_search(api_client, catalog, q, expected):
    assert set(slugs(api_client.get(reverse("search"), {"q": q}))) == expected


def test_search_by_sku(api_client, catalog):
    sku = catalog["b"].variants.first().sku
    assert slugs(api_client.get(reverse("search"), {"q": sku.lower()})) == ["lg-oled"]


def test_search_requires_query(api_client, catalog):
    assert api_client.get(reverse("search")).json()["error"]["code"] == "query_required"


def test_search_text_updates_on_brand_rename(api_client, catalog):
    lg = catalog["b"].brand
    lg.name = "Goldstar"
    lg.save()
    assert slugs(api_client.get(reverse("search"), {"q": "goldstar"})) == ["lg-oled"]


def test_suggest(api_client, catalog):
    data = api_client.get(reverse("search-suggest"), {"q": "qled"}).json()
    assert {p["slug"] for p in data["products"]} == {"samsung-qled"}
    data = api_client.get(reverse("search-suggest"), {"q": "tele"}).json()
    assert data["categories"][0]["slug"] == "televizorlar"
    assert api_client.get(reverse("search-suggest"), {"q": "s"}).json()["products"] == []


def test_compare(api_client, catalog):
    ids = f"{catalog['a'].id},{catalog['c'].id}"
    data = api_client.get(reverse("compare"), {"products": ids}).json()
    assert [p["slug"] for p in data["products"]] == ["samsung-qled", "samsung-crystal"]
    rows = {r["code"]: r for r in data["attributes"]}
    assert rows["color"]["values"] == ["Qora", "Qora"] and rows["color"]["is_different"] is False
    assert rows["screen_size"]["is_different"] is True
    assert api_client.get(reverse("compare"), {"products": "a,b"}).status_code == 400


def test_similar(api_client, catalog):
    data = api_client.get(reverse("product-similar", args=["samsung-qled"])).json()
    assert [p["slug"] for p in data] == []  # +-30% narx oralig'ida boshqa TV yo'q
    f.product(catalog["tv"], price="8500000", slug="near")
    data = api_client.get(reverse("product-similar", args=["samsung-qled"])).json()
    assert [p["slug"] for p in data] == ["near"]


def test_favorites(auth_client, catalog):
    url = reverse("favorite-list")
    assert auth_client.post(url, {"product_id": catalog["a"].id}, format="json").status_code == 201
    assert (
        auth_client.post(url, {"product_id": catalog["a"].id}, format="json").status_code == 201
    )  # idempotent
    assert [p["slug"] for p in auth_client.get(url).json()] == ["samsung-qled"]
    draft = Product.objects.get(slug="draft-one")
    assert auth_client.post(url, {"product_id": draft.id}, format="json").status_code == 404
    assert auth_client.delete(reverse("favorite-delete", args=[catalog["a"].id])).status_code == 204
    assert auth_client.get(url).json() == []


def test_favorites_require_auth(api_client):
    assert api_client.get(reverse("favorite-list")).status_code == 401


def test_compare_list_limit(auth_client, catalog):
    url = reverse("compare-list")
    products = [f.product(catalog["tv"]) for _ in range(6)]
    for p in products:
        assert auth_client.post(url, {"product_id": p.id}, format="json").status_code == 201
    resp = auth_client.post(url, {"product_id": catalog["a"].id}, format="json")
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "limit_reached"


def test_card_has_default_variant_for_quick_add(api_client, catalog):
    card = next(
        p for p in api_client.get(reverse("product-list")).json()["results"] if p["slug"] == "samsung-qled"
    )
    assert card["variant_id"] == catalog["a"].variants.order_by("price").first().id
    assert card["category_slug"] == "televizorlar"


def test_category_tree_keeps_child_sorted_before_parent(api_client):
    from apps.catalog.models import Category

    parent = Category.objects.create(slug="maishiy", name={"uz": "Maishiy"}, sort=5)
    Category.objects.create(slug="gaz-plitalar", name={"uz": "Gaz plitalar"}, parent=parent, sort=0)
    tree = api_client.get(reverse("category-tree")).json()
    assert [c["slug"] for c in tree[0]["children"]] == ["gaz-plitalar"]


def test_compare_includes_full_specs(api_client, catalog):
    """AI yig'gan to'liq xususiyatlar ham solishtiriladi; atributda bor nom takrorlanmaydi."""
    a, c = catalog["a"], catalog["c"]
    spec = lambda name, value: {"group": {"uz": "Asosiy"}, "name": {"uz": name}, "value": {"uz": value}}  # noqa: E731
    color = Attribute.objects.get(code="color").name["uz"]
    a.specs = [spec("HDMI portlar", "4"), spec(color, "takror")]
    c.specs = [spec("HDMI portlar", "2"), spec("Wi-Fi", "bor")]
    a.save()
    c.save()
    data = api_client.get(reverse("compare"), {"products": f"{a.id},{c.id}"}).json()
    rows = {r["name"]: r for r in data["attributes"]}
    assert rows["HDMI portlar"]["values"] == ["4", "2"] and rows["HDMI portlar"]["is_different"]
    assert rows["Wi-Fi"]["values"] == [None, "bor"]
    assert rows[color]["values"] == ["Qora", "Qora"]  # atribut qiymati, spec emas
