from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ApiError

from . import services
from .models import Cart, CartItem
from .serializers import CartAddSerializer, CartMergeSerializer, CartQtySerializer, CartSummarySerializer

TOKEN_PARAM = OpenApiParameter(
    "X-Cart-Token", str, OpenApiParameter.HEADER, description="Mehmon savati tokeni (login qilmagan xaridor)"
)


def cart_response(request, cart, code=status.HTTP_200_OK):
    data = CartSummarySerializer(services.summarize(cart), context={"request": request}).data
    resp = Response(data, status=code)
    if data["guest_token"]:
        resp["X-Cart-Token"] = data["guest_token"]
    return resp


@extend_schema(tags=["cart"], parameters=[TOKEN_PARAM])
class CartView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return cart_response(request, services.get_cart(request))

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def delete(self, request):
        cart = services.get_cart(request)
        if cart:
            cart.items.all().delete()
        return cart_response(request, cart)


@extend_schema(tags=["cart"], parameters=[TOKEN_PARAM])
class CartItemsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=CartAddSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        ser = CartAddSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        cart = services.get_cart(request, create=True)
        services.add_item(cart, ser.validated_data["variant_id"], ser.validated_data["qty"])
        return cart_response(request, cart, status.HTTP_201_CREATED)


@extend_schema(tags=["cart"], parameters=[TOKEN_PARAM])
class CartItemDetailView(APIView):
    permission_classes = [AllowAny]

    def _item(self, request, pk) -> CartItem:
        cart = services.get_cart(request)
        if cart is None:
            raise ApiError("not_found", "Savat topilmadi.", status_code=404)
        return get_object_or_404(CartItem, pk=pk, cart=cart)

    @extend_schema(request=CartQtySerializer, responses={200: OpenApiTypes.OBJECT})
    def patch(self, request, pk):
        item = self._item(request, pk)
        ser = CartQtySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.set_qty(item, ser.validated_data["qty"])
        return cart_response(request, item.cart)

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def delete(self, request, pk):
        item = self._item(request, pk)
        cart = item.cart
        item.delete()
        return cart_response(request, cart)


@extend_schema(tags=["cart"])
class CartMergeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CartMergeSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        ser = CartMergeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        target, _ = Cart.objects.get_or_create(user=request.user)
        guest = Cart.objects.filter(guest_token=ser.validated_data["guest_token"], user__isnull=True).first()
        if guest:
            services.merge(guest, target)
        return cart_response(request, target)
