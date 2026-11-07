from django.urls import path

from apps.accounts.views import AddressDetailView, AddressListCreateView, MeView

urlpatterns = [
    path("me", MeView.as_view(), name="me"),
    path("me/addresses", AddressListCreateView.as_view(), name="address-list"),
    path("me/addresses/<int:pk>", AddressDetailView.as_view(), name="address-detail"),
]
