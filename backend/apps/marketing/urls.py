from django.urls import path

from . import loyalty_views, sales_views, views

urlpatterns = [
    path("banners", views.BannerListView.as_view(), name="banners"),
    path("site", views.SiteContentView.as_view(), name="site-content"),
    path("promo/check", sales_views.PromoCheckView.as_view(), name="promo-check"),
    path("stock-requests", sales_views.StockRequestView.as_view(), name="stock-request"),
    path("quick-orders", sales_views.QuickOrderView.as_view(), name="quick-order"),
    path("deals", loyalty_views.DealListView.as_view(), name="deals"),
    path("products/<slug:slug>/bundles", loyalty_views.ProductBundlesView.as_view(), name="product-bundles"),
    path("bonus", loyalty_views.BonusInfoView.as_view(), name="bonus-info"),
    path("me/bonus", loyalty_views.MyBonusView.as_view(), name="my-bonus"),
]
