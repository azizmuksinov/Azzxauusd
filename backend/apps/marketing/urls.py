from django.urls import path

from . import sales_views, views

urlpatterns = [
    path("banners", views.BannerListView.as_view(), name="banners"),
    path("site", views.SiteContentView.as_view(), name="site-content"),
    path("promo/check", sales_views.PromoCheckView.as_view(), name="promo-check"),
    path("stock-requests", sales_views.StockRequestView.as_view(), name="stock-request"),
    path("quick-orders", sales_views.QuickOrderView.as_view(), name="quick-order"),
]
