"""Xodimlar uchun API: /api/v1/admin/... Har bir view o'z rolini tekshiradi."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.accounts.admin_api import StaffViewSet
from apps.ai_cards import admin_api as ai_cards
from apps.backoffice import admin_api as backoffice
from apps.backoffice import reports
from apps.catalog import admin_api as catalog
from apps.core.admin_api import SettingsView
from apps.delivery import admin_api as delivery
from apps.inventory import admin_api as inventory
from apps.logistics import admin_api as logistics
from apps.logistics import pickup_api
from apps.marketing import loyalty_views as loyalty
from apps.marketing import sales_views as sales
from apps.marketing import views as marketing
from apps.reviews.views import QuestionAdminViewSet, ReviewAdminViewSet
from apps.support.views import ChatAdminViewSet

router = SimpleRouter(trailing_slash=False)
router.register("categories", catalog.CategoryAdminViewSet, basename="admin-category")
router.register("brands", catalog.BrandAdminViewSet, basename="admin-brand")
router.register("attributes", catalog.AttributeAdminViewSet, basename="admin-attribute")
router.register("products", catalog.ProductAdminViewSet, basename="admin-product")
router.register("variants", catalog.VariantAdminViewSet, basename="admin-variant")
router.register("product-images", catalog.ProductImageAdminViewSet, basename="admin-product-image")
router.register("imports", catalog.ImportAdminViewSet, basename="admin-import")
router.register("warehouses", inventory.WarehouseViewSet, basename="admin-warehouse")
router.register("backoffice/suppliers", backoffice.SupplierViewSet, basename="bo-supplier")
router.register("backoffice/receipts", backoffice.ReceiptViewSet, basename="bo-receipt")
router.register("backoffice/transfers", backoffice.TransferViewSet, basename="bo-transfer")
router.register("backoffice/write-offs", backoffice.WriteOffViewSet, basename="bo-writeoff")
router.register("backoffice/cash-accounts", backoffice.CashAccountViewSet, basename="bo-cash-account")
router.register("backoffice/cash", backoffice.CashTransactionViewSet, basename="bo-cash")
router.register("ai-cards/batches", ai_cards.BatchViewSet, basename="ai-batch")
router.register("ai-cards/drafts", ai_cards.DraftViewSet, basename="ai-draft")
router.register("reviews", ReviewAdminViewSet, basename="admin-review")
router.register("staff", StaffViewSet, basename="admin-staff")
router.register("chats", ChatAdminViewSet, basename="admin-chat")
router.register("marketing/banners", marketing.BannerAdminViewSet, basename="admin-banner")
router.register("marketing/promos", sales.PromoCodeAdminViewSet, basename="admin-promo")
router.register("stock-requests", sales.StockRequestAdminViewSet, basename="admin-stock-request")
router.register("quick-orders", sales.QuickOrderAdminViewSet, basename="admin-quick-order")
router.register("marketing/deals", loyalty.DealAdminViewSet, basename="admin-deal")
router.register("marketing/bundles", loyalty.BundleAdminViewSet, basename="admin-bundle")
router.register("bonus", loyalty.BonusAdminViewSet, basename="admin-bonus")
router.register("questions", QuestionAdminViewSet, basename="admin-question")
router.register("pickup-points", pickup_api.PickupPointAdminViewSet, basename="admin-pickup-point")
router.register("orders", delivery.StaffOrderViewSet, basename="admin-order")
router.register("couriers", delivery.CourierViewSet, basename="admin-courier")
router.register("route-sheets", delivery.RouteSheetViewSet, basename="admin-route-sheet")
router.register("courier-cash/handovers", delivery.CashHandoverViewSet, basename="admin-cash-handover")
router.register("delivery-zones", logistics.DeliveryZoneViewSet, basename="admin-delivery-zone")
router.register("delivery-tariffs", logistics.DeliveryTariffViewSet, basename="admin-delivery-tariff")

urlpatterns = [
    path("settings", SettingsView.as_view(), name="admin-settings"),
    path("ai-cards/settings", ai_cards.AiSettingsView.as_view(), name="ai-settings"),
    path("ai-cards/check", ai_cards.AiCheckView.as_view(), name="ai-check"),
    path("ai-cards/market-price", ai_cards.MarketPriceView.as_view(), name="ai-market-price"),
    path("ai-cards/find-images/<int:product_id>", ai_cards.FindImagesView.as_view(), name="ai-find-images"),
    path("marketing/discount", marketing.BulkDiscountView.as_view(), name="admin-bulk-discount"),
    path("leads/summary", sales.LeadsSummaryView.as_view(), name="admin-leads-summary"),
    path("marketing/variants", loyalty.VariantPickView.as_view(), name="admin-variant-pick"),
    path("reports/sales", reports.SalesReportView.as_view(), name="admin-sales-report"),
    path("site", marketing.SiteContentAdminView.as_view(), name="admin-site-content"),
    path("backoffice/stock-valuation", backoffice.StockValuationView.as_view(), name="bo-stock-valuation"),
    path("courier-cash", delivery.CourierCashView.as_view(), name="admin-courier-cash"),
    path("stock", inventory.StockListView.as_view(), name="admin-stock"),
    path("stock/receipts", inventory.ReceiptView.as_view(), name="admin-stock-receipt"),
    path("stock/adjustments", inventory.AdjustmentView.as_view(), name="admin-stock-adjustment"),
    path("stock/movements", inventory.MovementListView.as_view(), name="admin-stock-movements"),
    path("serials", inventory.SerialUnitListView.as_view(), name="admin-serials"),
    path("serials/<int:pk>", inventory.SerialUnitDetailView.as_view(), name="admin-serial-detail"),
    *router.urls,
]
