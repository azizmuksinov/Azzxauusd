"""Kuryer ilovasi API: /api/v1/courier/...

Faqat `courier` roli va kuryer profili bor foydalanuvchi. Kuryer faqat o'ziga berilgan marshrutni ko'radi.
"""

import segno
from django.conf import settings
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ApiError
from apps.core.permissions import HasRole
from apps.orders.models import OrderItem
from apps.payments import services as payments
from apps.payments.models import Payment, Provider
from apps.payments.providers import click, payme

from . import serializers as s
from . import services
from .models import CashHandover, CodCollection, Courier, RouteSheet, RouteStop


class IsCourier(BasePermission):
    def has_permission(self, request, view) -> bool:
        if not HasRole.of("courier")().has_permission(request, view):
            return False
        courier = Courier.objects.filter(user=request.user, is_active=True).select_related("user").first()
        request.courier = courier
        return courier is not None


class _CourierView(APIView):
    permission_classes = [IsCourier]

    def _stop(self, request, pk) -> RouteStop:
        return get_object_or_404(
            RouteStop.objects.select_related("route", "order"), pk=pk, route__courier=request.courier
        )

    def _stop_response(self, request, stop: RouteStop, status_code=200):
        stop = RouteStop.objects.select_related("order").prefetch_related("order__items").get(pk=stop.pk)
        return Response(s.RouteStopSerializer(stop, context={"request": request}).data, status=status_code)


def _routes(courier):
    return (
        RouteSheet.objects.filter(courier=courier)
        .select_related("courier__user", "warehouse")
        .prefetch_related(
            Prefetch(
                "stops",
                queryset=RouteStop.objects.select_related("order").prefetch_related(
                    Prefetch("order__items", queryset=OrderItem.objects.order_by("id"))
                ),
            )
        )
    )


@extend_schema(tags=["courier"])
class CourierMeView(_CourierView):
    @extend_schema(responses=s.CourierSerializer)
    def get(self, request):
        return Response(s.CourierSerializer(request.courier).data)


@extend_schema(tags=["courier"])
class CourierRouteListView(_CourierView):
    """Mening marshrutlarim.

    Standart: faol (berilgan) marshrutlar; `?status=closed` — yopilganlar (oxirgi 20 ta).
    """

    @extend_schema(responses=s.RouteSheetListSerializer(many=True))
    def get(self, request):
        status = request.query_params.get("status", RouteSheet.Status.ISSUED)
        if status not in (RouteSheet.Status.ISSUED, RouteSheet.Status.CLOSED):
            raise ApiError("bad_status", "status: issued yoki closed.")
        qs = _routes(request.courier).filter(status=status)[:20]
        return Response(s.RouteSheetListSerializer(qs, many=True).data)


@extend_schema(tags=["courier"])
class CourierRouteDetailView(_CourierView):
    @extend_schema(responses=s.RouteSheetDetailSerializer)
    def get(self, request, pk):
        route = get_object_or_404(_routes(request.courier).exclude(status=RouteSheet.Status.DRAFT), pk=pk)
        return Response(s.RouteSheetDetailSerializer(route, context={"request": request}).data)


@extend_schema(tags=["courier"])
class StopStartView(_CourierView):
    """Mijozga yo'l oldim: buyurtma `out_for_delivery`, mijozga SMS."""

    @extend_schema(request=None, responses=s.RouteStopSerializer)
    def post(self, request, pk):
        stop = services.start_stop(self._stop(request, pk), request.courier)
        return self._stop_response(request, stop)


@extend_schema(tags=["courier"])
class StopDeliverView(_CourierView):
    """Mijoz tovarni ko'rib qabul qildi — topshirish akti. Qolgan summa naqd yoki QR orqali."""

    @extend_schema(request=s.DeliverSerializer, responses=s.HandoverActSerializer)
    def post(self, request, pk):
        stop = self._stop(request, pk)
        ser = s.DeliverSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        act = services.deliver(
            stop,
            request.courier,
            door_payment=d["door_payment"],
            inspection=d["inspection"],
            received_by=d["received_by"],
            comment=d["comment"],
            lat=d.get("latitude"),
            lng=d.get("longitude"),
        )
        return Response(s.HandoverActSerializer(act).data, status=201)


@extend_schema(tags=["courier"])
class StopRefuseView(_CourierView):
    """Mijoz tovarni eshik oldida rad etdi (sababi bilan)."""

    @extend_schema(request=s.RefuseSerializer, responses=s.RouteStopSerializer)
    def post(self, request, pk):
        stop = self._stop(request, pk)
        ser = s.RefuseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        services.refuse(
            stop,
            request.courier,
            reason=d["reason"],
            comment=d["comment"],
            lat=d.get("latitude"),
            lng=d.get("longitude"),
        )
        return self._stop_response(request, stop)


@extend_schema(tags=["courier"])
class StopFailView(_CourierView):
    """Yetkazib bo'lmadi: mijoz uyda yo'q, telefonni ko'tarmadi, manzil noto'g'ri, boshqa vaqt so'radi."""

    @extend_schema(request=s.FailSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        stop = self._stop(request, pk)
        ser = s.FailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        info = services.fail(
            stop,
            request.courier,
            outcome=d["outcome"],
            comment=d["comment"],
            lat=d.get("latitude"),
            lng=d.get("longitude"),
        )
        return Response(info)


def _qr_svg(url: str) -> str:
    return segno.make(url, error="m").svg_inline(scale=6, border=2)


@extend_schema(tags=["courier"])
class StopQrView(_CourierView):
    """Mijoz qolgan summani o'z telefonidan to'lashi uchun Payme/Click havolasi va QR (SVG)."""

    @extend_schema(request=s.QrRequestSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        stop = self._stop(request, pk)
        ser = s.QrRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        provider = ser.validated_data["provider"]
        if provider not in settings.PAYMENT_PROVIDERS:
            raise ApiError("provider_disabled", "Bu to'lov tizimi hozircha ulanmagan.")
        order = stop.order
        if stop.result != "pending":
            raise ApiError(
                "stop_finished", "Bu buyurtma bo'yicha natija allaqachon kiritilgan.", status_code=409
            )
        payments.check_payable(order)
        amount = payments.amount_due(order)
        url = {"payme": payme.checkout_url, "click": click.checkout_url}[provider](order, amount)
        return Response(
            {"provider": provider, "amount": str(amount), "payment_url": url, "qr_svg": _qr_svg(url)}
        )


@extend_schema(tags=["courier"])
class StopDemoQrPayView(_CourierView):
    """FAQAT DEMO_MODE: mijoz QR orqali to'lagandek qilish (sinov uchun)."""

    @extend_schema(request=None, responses=s.RouteStopSerializer)
    def post(self, request, pk):
        if not settings.DEMO_MODE:
            raise ApiError("not_found", "Topilmadi.", status_code=404)
        stop = self._stop(request, pk)
        order = stop.order
        payments.check_payable(order)
        p = Payment.objects.create(
            order=order,
            provider=Provider.DEMO,
            provider_txn_id=f"demo-door-{timezone.now().timestamp()}",
            amount=payments.amount_due(order),
        )
        payments.mark_succeeded(p)
        return self._stop_response(request, stop)


@extend_schema(tags=["courier"])
class CourierCashView(_CourierView):
    """Mendagi naqd pul: topshirilmagan summalar va oxirgi topshirishlar."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        c = request.courier
        pending = CodCollection.objects.filter(courier=c, handover__isnull=True).select_related("order")
        handovers = CashHandover.objects.filter(courier=c).select_related("account", "accepted_by")[:20]
        return Response(
            {
                "outstanding": str(services.outstanding(c)),
                "collections": s.CodCollectionSerializer(pending, many=True).data,
                "handovers": s.CashHandoverSerializer(handovers, many=True).data,
            }
        )
