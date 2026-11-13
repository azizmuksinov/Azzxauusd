from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import ApiError
from .permissions import HasRole
from .settings_registry import REGISTRY, all_settings, set_setting


@extend_schema(tags=["admin: settings"])
class SettingsView(APIView):
    """Biznes sozlamalari. O'qish va o'zgartirish — faqat admin."""

    permission_classes = [HasRole.of("admin")]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(all_settings())

    @extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
    def patch(self, request):
        if not isinstance(request.data, dict) or not request.data:
            raise ApiError("validation_error", '{"kalit": qiymat} ko\'rinishida yuboring.')
        unknown = set(request.data) - set(REGISTRY)
        if unknown:
            raise ApiError("unknown_setting", f"Noma'lum sozlama: {', '.join(sorted(unknown))}")
        errors = {}
        for key, value in request.data.items():
            try:
                set_setting(key, value, user=request.user)
            except (ValueError, TypeError, ArithmeticError, DjangoValidationError) as exc:
                errors[key] = [str(exc) or "Qiymat noto'g'ri"]
        if errors:
            raise ApiError("validation_error", "Ba'zi qiymatlar noto'g'ri.", extra={"fields": errors})
        return Response(all_settings())
