from rest_framework import serializers

from apps.core.phone import InvalidPhone, normalize_phone
from apps.geo.models import District

from .models import Address, User


class PhoneField(serializers.CharField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            return normalize_phone(value)
        except InvalidPhone as exc:
            raise serializers.ValidationError(str(exc)) from exc


class OtpRequestSerializer(serializers.Serializer):
    phone = PhoneField(max_length=32)


class OtpRequestResponseSerializer(serializers.Serializer):
    expires_in = serializers.IntegerField(help_text="Kod amal qilish muddati, soniya")
    resend_in = serializers.IntegerField(help_text="Qayta yuborish mumkin bo'lguncha, soniya")
    debug_code = serializers.CharField(required=False, help_text="Faqat DEMO rejimda")


class OtpVerifySerializer(serializers.Serializer):
    phone = PhoneField(max_length=32)
    code = serializers.RegexField(r"^\d{4,8}$")


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    is_new_user = serializers.BooleanField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class MeSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "phone", "first_name", "last_name", "email", "language", "roles", "date_joined"]
        read_only_fields = ["id", "phone", "roles", "date_joined"]

    def get_roles(self, obj) -> list[str]:
        return sorted(obj.groups.values_list("name", flat=True))


class AddressSerializer(serializers.ModelSerializer):
    recipient_phone = PhoneField(max_length=32)
    district = serializers.PrimaryKeyRelatedField(queryset=District.objects.filter(is_active=True))

    class Meta:
        model = Address
        fields = [
            "id",
            "label",
            "district",
            "settlement",
            "street",
            "house",
            "apartment",
            "entrance",
            "floor",
            "elevator",
            "intercom",
            "landmark",
            "latitude",
            "longitude",
            "recipient_name",
            "recipient_phone",
            "is_default",
        ]

    def validate(self, attrs):
        lat, lng = attrs.get("latitude"), attrs.get("longitude")
        if (lat is None) != (lng is None):
            raise serializers.ValidationError({"latitude": "latitude va longitude birga beriladi."})
        # O'zbekiston chegaralari (taxminiy bounding box).
        if lat is not None and not (37.0 <= float(lat) <= 45.8 and 55.9 <= float(lng) <= 73.2):
            raise serializers.ValidationError({"latitude": "Koordinata O'zbekiston hududidan tashqarida."})
        return attrs
