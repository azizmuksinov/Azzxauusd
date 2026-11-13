from django.urls import path

from apps.accounts.views import (
    LogoutView,
    OtpRequestView,
    OtpVerifyView,
    StaffDemoView,
    StaffLoginView,
    TokenRefreshView,
)

urlpatterns = [
    path("otp/request", OtpRequestView.as_view(), name="otp-request"),
    path("otp/verify", OtpVerifyView.as_view(), name="otp-verify"),
    path("staff/login", StaffLoginView.as_view(), name="staff-login"),
    path("staff/demo", StaffDemoView.as_view(), name="staff-demo"),
    path("token/refresh", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout", LogoutView.as_view(), name="logout"),
]
