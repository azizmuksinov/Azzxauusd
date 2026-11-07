"""Xodimlar API: buyurtmalarni yig'ish, kuryerlar, marshrut varaqlari, kuryer naqd puli.

Rollar: warehouse (yig'ish, marshrutni berish/yopish), logistics_manager (marshrut, kuryerlar),
finance (naqd qabul qilish), support (faqat ko'rish), admin (hammasi).
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.backoffice.models import CashAccount
from apps.catalog.admin_api import AdminPagination
from apps.core.exceptions import ApiError
from apps.core.permissions import HasRole
from apps.inventory.models import Warehouse
from apps.orders.models import Order, OrderItem

from . import serializers as s
from . import services
from .models import CashHandover, CodCollection, Courier, RouteSheet, RouteStop

ReadRoles = HasRole.of("warehouse", "logistics_manager", "support", "finance")
WarehouseRoles = HasRole.of("warehouse", "logistics_manager")
LogisticsRole = HasRole.of("logistics_manager")
FinanceRole = HasRole.of("finance")


def _order_qs():
    return Order.objects.prefetch_related(
        Prefetch("items", queryset=OrderItem.objects.select_related("variant__product").order_by("id")),
        Prefetch("route_stops", queryset=RouteStop.objects.filter(is_open=True).select_related("route")),
    )


@extend_schema(tags=["admin-delivery"])
class StaffOrderViewSet(viewsets.ReadOnlyModelViewSet):
    """Buyurtmalar (xodimlar uchun).

    Filtrlar: `status` va `payment_status` (vergul bilan), `q` (raqam/telefon), `unrouted=1`.
    """

    lookup_field = "number"
    pagination_class = AdminPagination

    def get_permissions(self):
        if self.action == "refund":
            return [FinanceRole()]
        return [(ReadRoles if self.action in ("list", "retrieve") else WarehouseRoles)()]

    def get_serializer_class(self):
        return s.StaffOrderListSerializer if self.action == "list" else s.StaffOrderDetailSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, description="Masalan: paid,cod_confirmed,picking"),
            OpenApiParameter("payment_status", str, description="Masalan: refund_pending"),
            OpenApiParameter("q", str),
            OpenApiParameter("unrouted", bool, description="Ochiq marshrutda bo'lmaganlar"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = _order_qs()
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("payment_status"):
            qs = qs.filter(payment_status__in=p["payment_status"].split(","))
        if p.get("q"):
            q = p["q"].strip()
            qs = qs.filter(
                Q(number__icontains=q) | Q(recipient_phone__contains=q) | Q(user__phone__contains=q)
            )
        if p.get("unrouted") in ("1", "true"):
            qs = qs.exclude(route_stops__is_open=True)
        if self.action == "retrieve":
            qs = qs.prefetch_related("history", "delivery_attempts__courier__user")
        return qs.order_by("created_at", "id") if p.get("status") or p.get("payment_status") else qs

    def _detail(self, order):
        order = _order_qs().prefetch_related("history").get(pk=order.pk)
        return Response(s.StaffOrderDetailSerializer(order, context={"request": self.request}).data)

    @extend_schema(request=None, responses=s.StaffOrderDetailSerializer)
    @action(detail=True, methods=["post"], url_path="start-picking")
    def start_picking(self, request, number=None):
        order = services.start_picking(self.get_object(), request.user)
        return self._detail(order)

    @extend_schema(request=s.PackSerializer, responses=s.StaffOrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def pack(self, request, number=None):
        ser = s.PackSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        order = services.pack(self.get_object(), request.user, ser.validated_data["serials"])
        return self._detail(order)

    @extend_schema(request=s.RefundSerializer, responses=s.StaffOrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def refund(self, request, number=None):
        """Mijozga pul qaytarildi (kassa yoki bank orqali) — kassadan chiqim yoziladi."""
        from apps.payments.services import refund_manually

        ser = s.RefundSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        account = get_object_or_404(CashAccount, pk=d["account"])
        order = refund_manually(
            self.get_object(),
            account=account,
            user=request.user,
            amount=d.get("amount"),
            comment=d["comment"],
        )
        return self._detail(order)


@extend_schema(tags=["admin-delivery"])
class CourierViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    """Kuryerlar.

    Yaratish: telefon bo'yicha foydalanuvchi topiladi yoki yaratiladi va `courier` roli beriladi.
    """

    serializer_class = s.CourierSerializer
    queryset = Courier.objects.select_related("user")
    http_method_names = ["get", "post", "patch"]

    def get_permissions(self):
        return [(ReadRoles if self.action in ("list", "retrieve") else LogisticsRole)()]

    @extend_schema(request=s.CourierCreateSerializer, responses={201: s.CourierSerializer})
    @transaction.atomic
    def create(self, request):
        ser = s.CourierCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        user, _ = get_user_model().objects.get_or_create(
            phone=d["phone"], defaults={"first_name": d["first_name"], "last_name": d["last_name"]}
        )
        if Courier.objects.filter(user=user).exists():
            raise ApiError("courier_exists", "Bu telefon raqamli kuryer allaqachon bor.", status_code=409)
        user.groups.add(Group.objects.get(name="courier"))
        warehouse = get_object_or_404(Warehouse, pk=d["warehouse"]) if d.get("warehouse") else None
        courier = Courier.objects.create(user=user, vehicle=d["vehicle"], warehouse=warehouse)
        return Response(s.CourierSerializer(courier).data, status=201)


@extend_schema(tags=["admin-delivery"])
class RouteSheetViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Marshrut varaqlari: qoralama → kuryerga berildi → yopildi."""

    pagination_class = AdminPagination

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [ReadRoles()]
        if self.action in ("issue", "close"):
            return [WarehouseRoles()]
        return [LogisticsRole()]

    def get_serializer_class(self):
        return s.RouteSheetListSerializer if self.action == "list" else s.RouteSheetDetailSerializer

    def get_queryset(self):
        qs = RouteSheet.objects.select_related("courier__user", "warehouse").prefetch_related(
            Prefetch(
                "stops",
                queryset=RouteStop.objects.select_related("order").prefetch_related(
                    Prefetch("order__items", queryset=OrderItem.objects.order_by("id"))
                ),
            )
        )
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("date"):
            qs = qs.filter(date=p["date"])
        if p.get("courier"):
            qs = qs.filter(courier_id=p["courier"])
        return qs

    def _detail(self, route):
        return Response(
            s.RouteSheetDetailSerializer(
                self.get_queryset().get(pk=route.pk), context={"request": self.request}
            ).data
        )

    @extend_schema(request=s.RouteCreateSerializer, responses={201: s.RouteSheetDetailSerializer})
    @transaction.atomic
    def create(self, request):
        ser = s.RouteCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        warehouse = get_object_or_404(Warehouse, pk=d["warehouse"], is_active=True)
        route = services.create_route(
            courier=d["courier"], warehouse=warehouse, date=d["date"], user=request.user, comment=d["comment"]
        )
        if d["orders"]:
            services.add_orders(route, d["orders"], request.user)
        resp = self._detail(route)
        resp.status_code = 201
        return resp

    @extend_schema(request=s.AddOrdersSerializer, responses=s.RouteSheetDetailSerializer)
    @action(detail=True, methods=["post"], url_path="stops")
    def add_stops(self, request, pk=None):
        ser = s.AddOrdersSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        route = self.get_object()
        services.add_orders(route, ser.validated_data["orders"], request.user)
        return self._detail(route)

    @extend_schema(request=None, responses=s.RouteSheetDetailSerializer)
    @action(detail=True, methods=["delete"], url_path=r"stops/(?P<stop_id>\d+)")
    def remove_stop(self, request, pk=None, stop_id=None):
        route = self.get_object()
        services.remove_stop(route, get_object_or_404(RouteStop, pk=stop_id, route=route))
        return self._detail(route)

    @extend_schema(request=None, responses=s.RouteSheetDetailSerializer)
    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        return self._detail(services.issue_route(self.get_object(), request.user))

    @extend_schema(request=None, responses=s.RouteSheetDetailSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return self._detail(services.close_route(self.get_object(), request.user))


@extend_schema(tags=["admin-delivery"])
class CourierCashView(APIView):
    """Kuryerlardagi topshirilmagan naqd pul (kassir uchun)."""

    permission_classes = [FinanceRole]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        rows = (
            CodCollection.objects.filter(handover__isnull=True)
            .values("courier_id")
            .annotate(amount=Sum("amount"), orders=Count("id"))
        )
        by_id = {r["courier_id"]: r for r in rows}
        couriers = Courier.objects.filter(pk__in=by_id).select_related("user")
        pending = CodCollection.objects.filter(handover__isnull=True).select_related("order")
        return Response(
            [
                {
                    "courier": s.CourierSerializer(c).data,
                    "amount": str(by_id[c.pk]["amount"]),
                    "orders": by_id[c.pk]["orders"],
                    "collections": s.CodCollectionSerializer(
                        [x for x in pending if x.courier_id == c.pk], many=True
                    ).data,
                }
                for c in couriers
            ]
        )


@extend_schema(tags=["admin-delivery"])
class CashHandoverViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Kuryerdan naqd qabul qilish (kassa hisobiga kirim) va tarix."""

    permission_classes = [FinanceRole]
    serializer_class = s.CashHandoverSerializer
    pagination_class = AdminPagination
    queryset = CashHandover.objects.select_related(
        "courier__user", "account", "accepted_by"
    ).prefetch_related("collections")

    @extend_schema(request=s.AcceptCashSerializer, responses={201: s.CashHandoverSerializer})
    def create(self, request):
        ser = s.AcceptCashSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        account = get_object_or_404(CashAccount, pk=d["account"])
        handover = services.accept_cash(
            courier=d["courier"],
            account=account,
            user=request.user,
            comment=d["comment"],
            collection_ids=d.get("collection_ids"),
        )
        return Response(s.CashHandoverSerializer(handover).data, status=201)
