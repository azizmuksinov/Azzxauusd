from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Address
from apps.cart.models import Cart
from apps.cart.services import summarize
from apps.core.exceptions import ApiError
from apps.core.i18n import request_language
from apps.logistics.services import quote_for_cart, validate_quote

from . import services
from .models import Order
from .payment_rules import payment_options
from .serializers import (
    CancelRequest,
    CheckoutRequest,
    DeliveryOptionsRequest,
    OrderDetailSerializer,
    OrderListSerializer,
    PlaceOrderRequest,
    TrackedOrderSerializer,
    TrackRequest,
)

IDEMPOTENCY = OpenApiParameter(
    "Idempotency-Key",
    str,
    OpenApiParameter.HEADER,
    required=True,
    description="Har bir buyurtma urinishi uchun yangi UUID. Takroriy so'rov o'sha buyurtmani qaytaradi.",
)


def _user_cart_summary(user):
    cart = Cart.objects.filter(user=user).first()
    summary = summarize(cart)
    services._ensure_cart_ok(summary)
    return cart, summary


def _address(user, address_id) -> Address:
    return get_object_or_404(Address.objects.select_related("district"), pk=address_id, user=user)


def _quote_payload(q) -> dict:
    return {
        "quote_id": str(q.public_id),
        "provider": q.provider,
        "delivery_price": str(q.delivery_price),
        "lifting": {
            "available": q.lifting_available,
            "price": str(q.lifting_price) if q.lifting_price else None,
        },
        "eta_days_min": q.eta_days_min,
        "eta_days_max": q.eta_days_max,
        "expires_at": q.expires_at,
    }


@extend_schema(tags=["checkout"])
class DeliveryOptionsView(APIView):
    """Manzil va joriy savat uchun yetkazish narxi va muddati (quote_id 15 daqiqa amal qiladi)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=DeliveryOptionsRequest, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        ser = DeliveryOptionsRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        address = _address(request.user, ser.validated_data["address_id"])
        _, summary = _user_cart_summary(request.user)
        return Response(_quote_payload(quote_for_cart(request.user, address, summary)))


def _pickup_point(point_id):
    from apps.logistics.models import PickupPoint

    return get_object_or_404(PickupPoint, pk=point_id, is_active=True)


@extend_schema(tags=["checkout"])
class CheckoutSummaryView(APIView):
    """Yakuniy summalar, bonus va ruxsat etilgan to'lov usullari (yetkazish yoki olib ketish)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=CheckoutRequest, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        from apps.marketing import bonus

        ser = CheckoutRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        _, summary = _user_cart_summary(request.user)
        if d.get("pickup_point_id"):
            point = _pickup_point(d["pickup_point_id"])
            quote, delivery = services.PickupQuote(), {"pickup_point": services._pickup_snapshot(point)}
        else:
            address = _address(request.user, d["address_id"])
            quote = validate_quote(d["quote_id"], request.user, address, summary)
            delivery = _quote_payload(quote)
        totals = services.checkout_totals(
            summary, quote, d["lifting"], d.get("promo_code", ""), request.user, d["use_bonus"]
        )
        goods = totals["subtotal"] - totals["discount_total"]
        return Response(
            {
                **{k: str(v) for k, v in totals.items()},
                "bundle_discount": str(summary.bundle_discount),
                "bonus": {
                    "enabled": bonus.enabled(),
                    "balance": str(bonus.balance(request.user)),
                    "usable": str(bonus.usable(request.user, goods)),
                    "will_earn": str(bonus.will_earn(goods - totals["bonus_spent"])),
                },
                "payment_methods": [
                    {
                        "code": o.code,
                        "available": o.available,
                        "required_prepayment": str(o.required_prepayment),
                        "note": o.reason,
                    }
                    for o in payment_options(totals["total"], totals["delivery_fee"] + totals["lifting_fee"])
                ],
                "delivery": delivery,
            }
        )


@extend_schema(tags=["orders"])
class OrderTrackView(APIView):
    """Buyurtmani raqami va telefon raqami bilan kuzatish (tizimga kirmasdan)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(request=TrackRequest, responses=TrackedOrderSerializer)
    def post(self, request):
        from apps.accounts.otp import RateLimited, _incr_window
        from apps.accounts.views import client_ip

        ser = TrackRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        ip = client_ip(request)
        # Raqamlarni saralab topishga qarshi: bitta manzildan soatiga cheklangan urinish.
        if ip and _incr_window(f"track:ip:{ip}", 3600) > 30:
            raise RateLimited()
        order = services.track(ser.validated_data["number"], ser.validated_data["phone"])
        if order is None:
            raise ApiError(
                "order_not_found",
                "Bunday buyurtma topilmadi. Raqam va telefonni tekshiring.",
                status_code=404,
            )
        return Response(TrackedOrderSerializer(order, context={"request": request}).data)


@extend_schema(tags=["orders"])
class OrderListCreateView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderListSerializer

    def get_queryset(self):
        qs = Order.objects.filter(user=self.request.user).prefetch_related("items")
        group = self.request.query_params.get("status")
        final = ["delivered", "returned", "cancelled", "refused_at_door"]
        if group == "active":
            qs = qs.exclude(status__in=final)
        elif group == "completed":
            qs = qs.filter(status__in=final)
        return qs

    @extend_schema(
        request=PlaceOrderRequest, responses={201: OrderDetailSerializer}, parameters=[IDEMPOTENCY]
    )
    def post(self, request):
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key or len(key) > 64:
            raise ApiError("idempotency_key_required", "Idempotency-Key sarlavhasi kerak (UUID).")
        ser = PlaceOrderRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        existing = Order.objects.filter(user=request.user, idempotency_key=key).first()
        if existing:
            return Response(OrderDetailSerializer(existing, context={"request": request}).data)
        point, address, name, phone = None, None, "", ""
        if d.get("pickup_point_id"):
            from apps.core.phone import InvalidPhone, normalize_phone

            point = _pickup_point(d["pickup_point_id"])
            name = d["recipient_name"].strip() or request.user.full_name or request.user.phone
            try:
                phone = (
                    normalize_phone(d["recipient_phone"])
                    if d["recipient_phone"].strip()
                    else request.user.phone
                )
            except InvalidPhone as exc:
                raise ApiError("validation_error", str(exc)) from exc
        else:
            address = _address(request.user, d["address_id"])
        cart = Cart.objects.filter(user=request.user).first()
        if cart is None:
            raise ApiError("cart_empty", "Savat bo'sh.")
        order, created = services.place_order(
            user=request.user,
            cart=cart,
            address=address,
            quote_id=d.get("quote_id"),
            payment_method=d["payment_method"],
            lifting=d["lifting"],
            comment=d["comment"],
            idempotency_key=key,
            language=request_language(request),
            promo_code=d.get("promo_code", ""),
            use_bonus=d["use_bonus"],
            pickup_point=point,
            recipient_name=name,
            recipient_phone=phone,
        )
        return Response(
            OrderDetailSerializer(order, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


@extend_schema(tags=["orders"])
class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderDetailSerializer
    lookup_field = "number"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items", "history")


@extend_schema(tags=["orders"])
class OrderCancelView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CancelRequest, responses=OrderDetailSerializer)
    def post(self, request, number):
        order = get_object_or_404(Order, number=number, user=request.user)
        ser = CancelRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        order = services.cancel_by_customer(order, ser.validated_data["reason"])
        return Response(OrderDetailSerializer(order, context={"request": request}).data)
