from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from apps.core.views import health

api_v1 = [
    path("auth/", include("apps.accounts.urls.auth")),
    path("", include("apps.accounts.urls.me")),
    path("geo/", include("apps.geo.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.cart.urls")),
    path("", include("apps.orders.urls")),
    path("admin/", include("config.admin_urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("health", health, name="health"),
    path("", SpectacularSwaggerView.as_view(url_name="schema")),
]
