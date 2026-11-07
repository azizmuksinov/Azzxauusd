"""Xodimlar uchun API: /api/v1/admin/... Har bir view o'z rolini tekshiradi."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.catalog import admin_api as catalog
from apps.inventory import admin_api as inventory

router = SimpleRouter(trailing_slash=False)
router.register("categories", catalog.CategoryAdminViewSet, basename="admin-category")
router.register("brands", catalog.BrandAdminViewSet, basename="admin-brand")
router.register("attributes", catalog.AttributeAdminViewSet, basename="admin-attribute")
router.register("products", catalog.ProductAdminViewSet, basename="admin-product")
router.register("variants", catalog.VariantAdminViewSet, basename="admin-variant")
router.register("product-images", catalog.ProductImageAdminViewSet, basename="admin-product-image")
router.register("imports", catalog.ImportAdminViewSet, basename="admin-import")
router.register("warehouses", inventory.WarehouseViewSet, basename="admin-warehouse")

urlpatterns = [
    path("stock", inventory.StockListView.as_view(), name="admin-stock"),
    path("stock/receipts", inventory.ReceiptView.as_view(), name="admin-stock-receipt"),
    path("stock/adjustments", inventory.AdjustmentView.as_view(), name="admin-stock-adjustment"),
    path("stock/movements", inventory.MovementListView.as_view(), name="admin-stock-movements"),
    path("serials", inventory.SerialUnitListView.as_view(), name="admin-serials"),
    path("serials/<int:pk>", inventory.SerialUnitDetailView.as_view(), name="admin-serial-detail"),
    *router.urls,
]
