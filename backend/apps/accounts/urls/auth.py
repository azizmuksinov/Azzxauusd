from django.urls import path

from apps.accounts.views import LogoutView, OtpRequestView, OtpVerifyView, TokenRefreshView

urlpatterns = [
    path("otp/request", OtpRequestView.as_view(), name="otp-request"),
    path("otp/verify", OtpVerifyView.as_view(), name="otp-verify"),
    path("token/refresh", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout", LogoutView.as_view(), name="logout"),
]
