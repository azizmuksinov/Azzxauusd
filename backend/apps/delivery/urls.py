from django.urls import path

from . import courier_api as v

urlpatterns = [
    path("courier/me", v.CourierMeView.as_view(), name="courier-me"),
    path("courier/cash", v.CourierCashView.as_view(), name="courier-cash"),
    path("courier/routes", v.CourierRouteListView.as_view(), name="courier-routes"),
    path("courier/routes/<int:pk>", v.CourierRouteDetailView.as_view(), name="courier-route"),
    path("courier/stops/<int:pk>/start", v.StopStartView.as_view(), name="courier-stop-start"),
    path("courier/stops/<int:pk>/deliver", v.StopDeliverView.as_view(), name="courier-stop-deliver"),
    path("courier/stops/<int:pk>/refuse", v.StopRefuseView.as_view(), name="courier-stop-refuse"),
    path("courier/stops/<int:pk>/fail", v.StopFailView.as_view(), name="courier-stop-fail"),
    path("courier/stops/<int:pk>/qr", v.StopQrView.as_view(), name="courier-stop-qr"),
    path(
        "courier/stops/<int:pk>/demo-qr-pay", v.StopDemoQrPayView.as_view(), name="courier-stop-demo-qr-pay"
    ),
]
