from django.urls import path

from . import views

urlpatterns = [
    path("checkout/delivery-options", views.DeliveryOptionsView.as_view(), name="checkout-delivery"),
    path("checkout/summary", views.CheckoutSummaryView.as_view(), name="checkout-summary"),
    path("orders", views.OrderListCreateView.as_view(), name="orders"),
    path("orders/<str:number>", views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:number>/cancel", views.OrderCancelView.as_view(), name="order-cancel"),
]
