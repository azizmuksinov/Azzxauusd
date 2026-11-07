import json

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.views import client_ip
from apps.core.exceptions import ApiError
from apps.orders.models import Order, PaymentMethod
from apps.orders.serializers import OrderDetailSerializer

from . import services
from .models import Payment, Provider, WebhookLog
from .providers import click, payme, uzum


def _ip_allowed(provider: str, ip: str | None) -> bool:
    allowed = settings.PAYMENT_ALLOWED_IPS.get(provider) or []
    return not allowed or ip in allowed


def _log(provider, request, body, valid, response) -> None:
    WebhookLog.objects.create(
        provider=provider,
        path=request.path[:128],
        ip=client_ip(request),
        body=body,
        signature_valid=valid,
        response=response,
    )


class _Webhook(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes: list = []


@extend_schema(tags=["webhooks"], request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
class PaymeWebhookView(_Webhook):
    parser_classes = [JSONParser]

    def post(self, request):
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": payme.PaymeError(payme.ERR_PARSE, "JSON xato").as_dict(),
            }
            _log(Provider.PAYME, request, None, None, resp)
            return Response(resp)
        valid = payme.check_auth(request.META.get("HTTP_AUTHORIZATION", "")) and _ip_allowed(
            Provider.PAYME, client_ip(request)
        )
        if not valid:
            resp = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": payme.PaymeError(payme.ERR_AUTH, "Ruxsat yo'q").as_dict(),
            }
        else:
            resp = payme.PaymeHandler().handle(body)
        _log(Provider.PAYME, request, body, valid, resp)
        return Response(resp)


@extend_schema(tags=["webhooks"], request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
class ClickWebhookView(_Webhook):
    parser_classes = [FormParser, MultiPartParser, JSONParser]
    click_action: int = 0  # `action` nomi DRF'da band

    def post(self, request):
        data = {k: (v[0] if isinstance(v, list) else v) for k, v in dict(request.data).items()}
        if not _ip_allowed(Provider.CLICK, client_ip(request)):
            resp, valid = click.ClickHandler._resp(data, click.ERR_SIGN, "IP ruxsat etilmagan"), False
        else:
            resp, valid = click.ClickHandler().handle(data, self.click_action)
        _log(Provider.CLICK, request, data, valid, resp)
        return Response(resp)


class ClickPrepareView(ClickWebhookView):
    click_action = click.ACTION_PREPARE


class ClickCompleteView(ClickWebhookView):
    click_action = click.ACTION_COMPLETE


@extend_schema(tags=["webhooks"], request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT})
class UzumWebhookView(_Webhook):
    parser_classes = [JSONParser]

    def post(self, request, operation):
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            resp = {"status": "FAILED", "errorCode": uzum.ERR_JSON, "timestamp": payme.now_ms()}
            _log(Provider.UZUM, request, None, None, resp)
            return Response(resp, status=400)
        valid = uzum.check_auth(request.META.get("HTTP_AUTHORIZATION", "")) and _ip_allowed(
            Provider.UZUM, client_ip(request)
        )
        if not valid:
            resp = {
                "serviceId": body.get("serviceId"),
                "timestamp": payme.now_ms(),
                "status": "FAILED",
                "errorCode": uzum.ERR_ACCESS_DENIED,
            }
            _log(Provider.UZUM, request, body, False, resp)
            return Response(resp, status=401)
        resp = uzum.UzumHandler().handle(operation, body)
        _log(Provider.UZUM, request, body, True, resp)
        return Response(resp, status=200 if resp.get("status") != "FAILED" else 400)


class PayRequest(serializers.Serializer):
    provider = serializers.ChoiceField(choices=[Provider.PAYME, Provider.CLICK, Provider.UZUM])
    return_url = serializers.URLField(required=False, allow_blank=True, default="")


@extend_schema(tags=["orders"])
class OrderPayView(APIView):
    """To'lov havolasi: xaridor shu manzilga yo'naltiriladi. Summa — to'liq yoki avans (yetkazish narxi)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=PayRequest, responses={200: OpenApiTypes.OBJECT})
    def post(self, request, number):
        order = get_object_or_404(Order, number=number, user=request.user)
        ser = PayRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        provider = ser.validated_data["provider"]
        if provider not in settings.PAYMENT_PROVIDERS:
            raise ApiError("provider_disabled", "Bu to'lov tizimi hozircha ulanmagan.")
        if order.payment_method in PaymentMethod.online() and order.payment_method != provider:
            raise ApiError("provider_mismatch", f"Buyurtma {order.payment_method} orqali to'lanadi.")
        services.check_payable(order)
        amount = services.amount_due(order)
        builder = {"payme": payme.checkout_url, "click": click.checkout_url, "uzum": uzum.checkout_url}[
            provider
        ]
        url = builder(order, amount, ser.validated_data["return_url"])
        if not url:
            raise ApiError(
                "provider_url_unavailable", "To'lov havolasi sozlanmagan — Uzum Bank ilovasi orqali to'lang."
            )
        return Response(
            {
                "provider": provider,
                "amount": str(amount),
                "payment_url": url,
                "payment_deadline": order.payment_deadline,
            }
        )


@extend_schema(tags=["orders"])
class DemoPayView(APIView):
    """FAQAT DEMO_MODE: to'lov tizimisiz buyurtmani "to'langan" deb belgilash (sinov uchun)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=OrderDetailSerializer)
    def post(self, request, number):
        if not settings.DEMO_MODE:
            raise ApiError("not_found", "Topilmadi.", status_code=404)
        order = get_object_or_404(Order, number=number, user=request.user)
        services.check_payable(order)
        p = Payment.objects.create(
            order=order,
            provider=Provider.DEMO,
            provider_txn_id=f"demo-{timezone.now().timestamp()}",
            amount=services.amount_due(order),
        )
        services.mark_succeeded(p)
        order.refresh_from_db()
        return Response(
            OrderDetailSerializer(order, context={"request": request}).data, status=status.HTTP_200_OK
        )
