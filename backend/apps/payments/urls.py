from django.urls import path

from . import views

urlpatterns = [
    path("webhooks/payme", views.PaymeWebhookView.as_view(), name="webhook-payme"),
    path("webhooks/click/prepare", views.ClickPrepareView.as_view(), name="webhook-click-prepare"),
    path("webhooks/click/complete", views.ClickCompleteView.as_view(), name="webhook-click-complete"),
    path("webhooks/uzum/<str:operation>", views.UzumWebhookView.as_view(), name="webhook-uzum"),
    path("orders/<str:number>/pay", views.OrderPayView.as_view(), name="order-pay"),
    path("orders/<str:number>/demo-pay", views.DemoPayView.as_view(), name="order-demo-pay"),
]
