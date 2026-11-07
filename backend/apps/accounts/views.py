from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView as _TokenRefreshView

from apps.core.exceptions import ApiError

from .models import Address
from .otp import request_otp, verify_otp
from .serializers import (
    AddressSerializer,
    LogoutSerializer,
    MeSerializer,
    OtpRequestResponseSerializer,
    OtpRequestSerializer,
    OtpVerifySerializer,
    TokenPairSerializer,
)

User = get_user_model()


def client_ip(request) -> str | None:
    # Reverse proxy (nginx) X-Forwarded-For'ni o'zi to'g'ri qo'yadi deb hisoblaymiz: birinchi qiymat.
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class OtpRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(request=OtpRequestSerializer, responses=OtpRequestResponseSerializer, tags=["auth"])
    def post(self, request):
        ser = OtpRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = request_otp(ser.validated_data["phone"], client_ip(request))
        body = {"expires_in": result.expires_in, "resend_in": result.resend_in}
        if result.debug_code:
            body["debug_code"] = result.debug_code
        return Response(body)


class OtpVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(request=OtpVerifySerializer, responses=TokenPairSerializer, tags=["auth"])
    def post(self, request):
        ser = OtpVerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        phone = ser.validated_data["phone"]
        verify_otp(phone, ser.validated_data["code"])

        with transaction.atomic():
            user, created = User.objects.get_or_create(phone=phone)
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
        if not user.is_active:
            raise ApiError("account_disabled", "Akkaunt bloklangan.", status_code=403)

        refresh = RefreshToken.for_user(user)
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh), "is_new_user": created}
        )


class LogoutView(APIView):
    @extend_schema(request=LogoutSerializer, responses={204: None}, tags=["auth"])
    def post(self, request):
        ser = LogoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            token = RefreshToken(ser.validated_data["refresh"])
            if str(token.get("user_id")) != str(request.user.pk):
                raise ApiError("token_invalid", "Token boshqa foydalanuvchiga tegishli.")
            token.blacklist()
        except TokenError as exc:
            raise ApiError("token_invalid", "Token yaroqsiz.") from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["me"])
class MeView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def perform_destroy(self, instance):
        instance.anonymize()


class AddressViewSetMixin:
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user).select_related("district")

    @transaction.atomic
    def _save(self, serializer, **kwargs):
        if serializer.validated_data.get("is_default"):
            Address.objects.filter(user=self.request.user, is_default=True).update(is_default=False)
        return serializer.save(**kwargs)


@extend_schema(tags=["me"])
class AddressListCreateView(AddressViewSetMixin, generics.ListCreateAPIView):
    pagination_class = None

    def perform_create(self, serializer):
        is_first = not Address.objects.filter(user=self.request.user).exists()
        if is_first:
            serializer.validated_data["is_default"] = True
        self._save(serializer, user=self.request.user)


@extend_schema(tags=["me"])
class AddressDetailView(AddressViewSetMixin, generics.RetrieveUpdateDestroyAPIView):
    def perform_update(self, serializer):
        self._save(serializer)

    @transaction.atomic
    def perform_destroy(self, instance):
        was_default = instance.is_default
        instance.delete()
        if was_default:
            nxt = Address.objects.filter(user=self.request.user).order_by("-created_at").first()
            if nxt:
                nxt.is_default = True
                nxt.save(update_fields=["is_default", "updated_at"])


@extend_schema(
    tags=["auth"],
    summary="Tokenni yangilash",
    description=(
        "Refresh token yuboriladi, javobda yangi access va refresh token qaytadi. "
        "Access token 15 daqiqa, refresh token 30 kun amal qiladi; eski refresh token qayta ishlamaydi."
    ),
)
class TokenRefreshView(_TokenRefreshView):
    pass
