from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny

from .models import District, Region
from .serializers import DistrictSerializer, RegionSerializer


class RegionListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegionSerializer
    pagination_class = None
    queryset = Region.objects.all()


class DistrictListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = DistrictSerializer
    pagination_class = None

    def get_queryset(self):
        region = get_object_or_404(Region, pk=self.kwargs["region_id"])
        return District.objects.filter(region=region, is_active=True)
