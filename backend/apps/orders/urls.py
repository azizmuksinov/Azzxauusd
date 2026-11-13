from django.urls import path

from apps.logistics.pickup_api import PickupPointListView

from . import views

urlpatterns = [
    path("checkout/delivery-options", views.DeliveryOptionsView.as_view(), name="checkout-delivery"),
    path("checkout/summary", views.CheckoutSummaryView.as_view(), name="checkout-summary"),
    path("pickup-points", PickupPointListView.as_view(), name="pickup-points"),
    path("orders", views.OrderListCreateView.as_view(), name="orders"),
    path("orders/track", views.OrderTrackView.as_view(), name="order-track"),
    path("orders/<str:number>", views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:number>/cancel", views.OrderCancelView.as_view(), name="order-cancel"),
]
