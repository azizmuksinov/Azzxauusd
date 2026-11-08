from django.urls import path

from . import views

urlpatterns = [
    path("products/<slug:slug>/reviews", views.ProductReviewsView.as_view(), name="product-reviews"),
]
