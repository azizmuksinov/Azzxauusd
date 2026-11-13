from django.urls import path

from .views import DistrictListView, RegionListView

urlpatterns = [
    path("regions", RegionListView.as_view(), name="geo-regions"),
    path("regions/<int:region_id>/districts", DistrictListView.as_view(), name="geo-districts"),
]
