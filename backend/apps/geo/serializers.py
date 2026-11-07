from rest_framework import serializers

from apps.core.i18n import localize, request_language

from .models import District, Region


class _LocalizedNameMixin(serializers.Serializer):
    name = serializers.SerializerMethodField()

    def get_name(self, obj) -> str:
        return localize(obj.name, request_language(self.context.get("request")))


class RegionSerializer(_LocalizedNameMixin, serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ["id", "name", "soato_code"]


class DistrictSerializer(_LocalizedNameMixin, serializers.ModelSerializer):
    class Meta:
        model = District
        fields = ["id", "region_id", "name"]
