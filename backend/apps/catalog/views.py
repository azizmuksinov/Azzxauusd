from django.conf import settings
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ApiError
from apps.core.i18n import localize, request_language

from .models import Brand, Category, CompareItem, Favorite, Product, ProductImage
from .search import get_search_backend
from .selectors import apply_filters, apply_sort, facets, public_products
from .serializers import (
    BrandSerializer,
    CategoryDetailSerializer,
    ProductCardSerializer,
    ProductDetailSerializer,
)

LIST_PARAMS = [
    OpenApiParameter("category", str, description="Kategoriya slug (ichki kategoriyalar bilan)"),
    OpenApiParameter("brand", str, description="Brend slug'lari, vergul bilan: samsung,lg"),
    OpenApiParameter("price_min", OpenApiTypes.DECIMAL),
    OpenApiParameter("price_max", OpenApiTypes.DECIMAL),
    OpenApiParameter("in_stock", bool),
    OpenApiParameter("q", str, description="Matnli qidiruv"),
    OpenApiParameter("sort", str, enum=["popular", "new", "price_asc", "price_desc", "rating", "relevance"]),
    OpenApiParameter(
        "f[code]",
        str,
        description="Xususiyat filtri: f[screen_size]=50..65, f[color]=black,white, f[smart_tv]=true",
    ),
    OpenApiParameter("lang", str, enum=["uz", "uz_cyrl", "ru"]),
]


class ProductPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 60


def with_card_prefetch(qs):
    return qs.prefetch_related(
        Prefetch("images", queryset=ProductImage.objects.order_by("sort", "id"), to_attr="prefetched_images")
    )


def build_product_queryset(request, *, category=None, require_query=False):
    params = request.query_params
    qs = apply_filters(public_products(), params, category=category)
    query = (params.get("q") or "").strip()
    if require_query and not query:
        raise ApiError("query_required", "Qidiruv so'zini kiriting (q).")
    relevance_ids = None
    if query:
        qs, relevance_ids = get_search_backend().filter_queryset(qs, query)
    sort = params.get("sort")
    if sort == "relevance" or (query and not sort):
        if relevance_ids:
            from django.db.models import Case, IntegerField, Value, When

            order = Case(
                *[When(pk=pk, then=Value(i)) for i, pk in enumerate(relevance_ids)],
                output_field=IntegerField(),
            )
            qs = qs.order_by(order)
        else:
            qs = apply_sort(qs, "popular")
    else:
        qs = apply_sort(qs, sort)
    return qs


class _Public:
    permission_classes = [AllowAny]


@extend_schema(tags=["catalog"])
class CategoryTreeView(_Public, APIView):
    @extend_schema(operation_id="categories_tree", responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        lang = request_language(request)
        cats = list(Category.objects.filter(is_active=True).order_by("sort", "id"))
        # Ikki bosqich: bola ota-onasidan oldin kelsa ham (sort kichik) yo'qolmaydi.
        nodes = {
            c.id: {"id": c.id, "slug": c.slug, "name": localize(c.name, lang), "icon": c.icon, "children": []}
            for c in cats
        }
        roots = []
        for c in cats:
            if c.parent_id is None:
                roots.append(nodes[c.id])
            elif c.parent_id in nodes:
                nodes[c.parent_id]["children"].append(nodes[c.id])
        return Response(roots)


@extend_schema(tags=["catalog"])
class CategoryDetailView(_Public, generics.RetrieveAPIView):
    serializer_class = CategoryDetailSerializer
    lookup_field = "slug"
    queryset = Category.objects.filter(is_active=True)


@extend_schema(tags=["catalog"], parameters=LIST_PARAMS, responses={200: OpenApiTypes.OBJECT})
class CategoryFiltersView(_Public, APIView):
    def get(self, request, slug):
        category = get_object_or_404(Category, slug=slug, is_active=True)
        qs = build_product_queryset(request, category=category)
        return Response(facets(qs, category, request_language(request)))


@extend_schema(tags=["catalog"])
class BrandListView(_Public, generics.ListAPIView):
    serializer_class = BrandSerializer
    pagination_class = None
    queryset = Brand.objects.filter(is_active=True)


@extend_schema(tags=["catalog"])
class BrandDetailView(_Public, generics.RetrieveAPIView):
    serializer_class = BrandSerializer
    lookup_field = "slug"
    queryset = Brand.objects.filter(is_active=True)


@extend_schema(tags=["catalog"], parameters=LIST_PARAMS)
class ProductListView(_Public, generics.ListAPIView):
    serializer_class = ProductCardSerializer
    pagination_class = ProductPagination
    require_query = False

    def get_queryset(self):
        category = None
        if slug := self.request.query_params.get("category"):
            category = get_object_or_404(Category, slug=slug, is_active=True)
        return with_card_prefetch(
            build_product_queryset(self.request, category=category, require_query=self.require_query)
        )


@extend_schema(tags=["catalog"], parameters=LIST_PARAMS)
class SearchView(ProductListView):
    require_query = True


@extend_schema(tags=["catalog"])
class ProductDetailView(_Public, generics.RetrieveAPIView):
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return public_products()


@extend_schema(tags=["catalog"])
class SimilarProductsView(_Public, generics.ListAPIView):
    serializer_class = ProductCardSerializer
    pagination_class = None

    def get_queryset(self):
        product = get_object_or_404(public_products(), slug=self.kwargs["slug"])
        qs = public_products().filter(category_id=product.category_id).exclude(pk=product.pk)
        if product.min_price:
            qs = qs.filter(
                min_price__gte=product.min_price * 7 / 10, min_price__lte=product.min_price * 13 / 10
            )
        return with_card_prefetch(qs.order_by("-available", "-rating_count", "id"))[:12]


@extend_schema(
    tags=["catalog"],
    parameters=[OpenApiParameter("q", str, required=True)],
    responses={200: OpenApiTypes.OBJECT},
)
class SearchSuggestView(_Public, APIView):
    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 2:
            return Response({"products": [], "categories": [], "brands": []})
        lang = request_language(request)
        qs, _ = get_search_backend().filter_queryset(public_products(), query)
        products = [
            {"slug": p.slug, "name": localize(p.name, lang)} for p in qs.order_by("-rating_count")[:6]
        ]
        cat_q = Q()
        for key in ("uz", "uz_cyrl", "ru"):
            cat_q |= Q(**{f"name__{key}__icontains": query})
        categories = [
            {"slug": c.slug, "name": localize(c.name, lang)}
            for c in Category.objects.filter(cat_q, is_active=True)[:4]
        ]
        brands = list(Brand.objects.filter(name__icontains=query, is_active=True).values("slug", "name")[:4])
        return Response({"products": products, "categories": categories, "brands": brands})


def _parse_ids(raw: str | None, limit: int) -> list[int]:
    try:
        ids = [int(x) for x in (raw or "").split(",") if x.strip()]
    except ValueError as exc:
        raise ApiError("invalid_ids", "products=1,2,3 ko'rinishida bering.") from exc
    if not ids:
        raise ApiError("invalid_ids", "Kamida bitta tovar kerak.")
    return list(dict.fromkeys(ids))[:limit]


def compare_table(products: list[Product], lang: str) -> dict:
    from .models import AttributeValue

    values = (
        AttributeValue.objects.filter(
            product__in=products, variant__isnull=True, attribute__is_comparable=True
        )
        .select_related("attribute", "option")
        .order_by("attribute__sort", "attribute__id")
    )
    table: dict[str, dict] = {}
    for av in values:
        row = table.setdefault(
            av.attribute.code,
            {
                "code": av.attribute.code,
                "name": localize(av.attribute.name, lang),
                "group": localize(av.attribute.group_name, lang),
                "values": {},
            },
        )
        row["values"][av.product_id] = av.display(lang)
    # To'liq xususiyatlar (Product.specs, AI kartochkadan): nomi bo'yicha; atributda bor nom takrorlanmaydi.
    known = {row["name"].strip().lower() for row in table.values()}
    for product in products:
        for spec in product.specs or []:
            if not isinstance(spec, dict):
                continue
            name, value = localize(spec.get("name"), lang), localize(spec.get("value"), lang)
            key = (name or "").strip().lower()
            if not key or not value or key in known:
                continue
            row = table.setdefault(
                f"spec:{key}",
                {
                    "code": f"spec:{key}",
                    "name": name,
                    "group": localize(spec.get("group"), lang),
                    "values": {},
                },
            )
            row["values"].setdefault(product.id, value)
    rows = []
    for row in table.values():
        vals = [row["values"].get(p.id) for p in products]
        rows.append({**row, "values": vals, "is_different": len(set(vals)) > 1})
    return {"attributes": rows}


@extend_schema(
    tags=["catalog"],
    parameters=[OpenApiParameter("products", str, required=True, description="1,2,3")],
    responses={200: OpenApiTypes.OBJECT},
)
class CompareView(_Public, APIView):
    def get(self, request):
        ids = _parse_ids(request.query_params.get("products"), settings.CATALOG_COMPARE_MAX)
        by_id = {p.id: p for p in with_card_prefetch(public_products().filter(pk__in=ids))}
        products = [by_id[i] for i in ids if i in by_id]
        ctx = {"request": request}
        return Response(
            {
                "products": ProductCardSerializer(products, many=True, context=ctx).data,
                **compare_table(products, request_language(request)),
            }
        )


class ProductIdSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()


class _UserProductListView(generics.GenericAPIView):
    """Sevimlilar va solishtirish ro'yxati uchun umumiy asos."""

    permission_classes = [IsAuthenticated]
    serializer_class = ProductIdSerializer
    model = None
    limit: int | None = None

    def _products(self):
        ids = list(self.model.objects.filter(user=self.request.user).values_list("product_id", flat=True))
        by_id = {p.id: p for p in with_card_prefetch(public_products().filter(pk__in=ids))}
        return [by_id[i] for i in ids if i in by_id]

    @extend_schema(responses=ProductCardSerializer(many=True))
    def get(self, request):
        return Response(ProductCardSerializer(self._products(), many=True, context={"request": request}).data)

    @extend_schema(request=ProductIdSerializer, responses={201: None})
    def post(self, request):
        ser = ProductIdSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        product = get_object_or_404(public_products(), pk=ser.validated_data["product_id"])
        if self.limit and self.model.objects.filter(user=request.user).count() >= self.limit:
            if not self.model.objects.filter(user=request.user, product=product).exists():
                raise ApiError("limit_reached", f"Ko'pi bilan {self.limit} ta tovar.")
        self.model.objects.get_or_create(user=request.user, product=product)
        return Response(status=status.HTTP_201_CREATED)


class _UserProductDeleteView(APIView):
    permission_classes = [IsAuthenticated]
    model = None

    @extend_schema(responses={204: None})
    def delete(self, request, product_id):
        self.model.objects.filter(user=request.user, product_id=product_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["me"])
class FavoriteListView(_UserProductListView):
    model = Favorite


@extend_schema(tags=["me"])
class FavoriteDeleteView(_UserProductDeleteView):
    model = Favorite


@extend_schema(tags=["me"])
class CompareListView(_UserProductListView):
    model = CompareItem
    limit = CompareItem.MAX_ITEMS


@extend_schema(tags=["me"])
class CompareDeleteView(_UserProductDeleteView):
    model = CompareItem
