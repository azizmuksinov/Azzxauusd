from django.urls import path

from . import views

urlpatterns = [
    path("categories", views.CategoryTreeView.as_view(), name="category-tree"),
    path("categories/<slug:slug>", views.CategoryDetailView.as_view(), name="category-detail"),
    path("categories/<slug:slug>/filters", views.CategoryFiltersView.as_view(), name="category-filters"),
    path("brands", views.BrandListView.as_view(), name="brand-list"),
    path("brands/<slug:slug>", views.BrandDetailView.as_view(), name="brand-detail"),
    path("products", views.ProductListView.as_view(), name="product-list"),
    path("products/<slug:slug>", views.ProductDetailView.as_view(), name="product-detail"),
    path("products/<slug:slug>/similar", views.SimilarProductsView.as_view(), name="product-similar"),
    path("search", views.SearchView.as_view(), name="search"),
    path("search/suggest", views.SearchSuggestView.as_view(), name="search-suggest"),
    path("compare", views.CompareView.as_view(), name="compare"),
    path("me/favorites", views.FavoriteListView.as_view(), name="favorite-list"),
    path("me/favorites/<int:product_id>", views.FavoriteDeleteView.as_view(), name="favorite-delete"),
    path("me/compare", views.CompareListView.as_view(), name="compare-list"),
    path("me/compare/<int:product_id>", views.CompareDeleteView.as_view(), name="compare-delete"),
]
