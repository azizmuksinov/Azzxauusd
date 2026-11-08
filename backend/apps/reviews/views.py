from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, serializers, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.catalog.admin_api import AdminPagination
from apps.catalog.selectors import public_products
from apps.core.exceptions import ApiError
from apps.core.permissions import HasRole

from . import services
from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ["id", "rating", "text", "pros", "cons", "author", "reply", "created_at"]
        read_only_fields = ["id", "author", "reply", "created_at"]

    def get_author(self, obj) -> str:
        name = (obj.user.first_name or "").strip()
        return f"{name} {obj.user.last_name[:1]}.".strip(" .") if name else "Xaridor"


class AdminReviewSerializer(ReviewSerializer):
    product = serializers.CharField(source="product.slug", read_only=True)

    class Meta(ReviewSerializer.Meta):
        fields = [*ReviewSerializer.Meta.fields, "product", "is_published"]
        read_only_fields = ["id", "author", "created_at", "rating", "text", "pros", "cons", "product"]


@extend_schema(tags=["reviews"])
class ProductReviewsView(generics.ListCreateAPIView):
    """Tovar sharhlari. Yozish — faqat tovarni olgan xaridor (buyurtmasi yetkazilgan), bir marta."""

    serializer_class = ReviewSerializer

    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == "POST" else [AllowAny()]

    def _product(self):
        return get_object_or_404(public_products(), slug=self.kwargs["slug"])

    def get_queryset(self):
        return Review.objects.filter(product__slug=self.kwargs["slug"], is_published=True).select_related(
            "user"
        )

    def list(self, request, *args, **kwargs):
        resp = super().list(request, *args, **kwargs)
        product = self._product()
        user = request.user
        can = (
            user.is_authenticated
            and not Review.objects.filter(product=product, user=user).exists()
            and services.has_received(user, product)
        )
        data = resp.data if isinstance(resp.data, dict) else {"results": resp.data}
        data.update(
            {
                "rating_avg": str(product.rating_avg),
                "rating_count": product.rating_count,
                "distribution": services.distribution(product),
                "can_review": bool(can),
            }
        )
        return Response(data)

    def perform_create(self, serializer):
        product = self._product()
        user = self.request.user
        if Review.objects.filter(product=product, user=user).exists():
            raise ApiError("already_reviewed", "Bu tovarga sharh qoldirgansiz.", status_code=409)
        if not services.has_received(user, product):
            raise ApiError(
                "not_purchased", "Sharhni faqat tovarni olgan xaridor yozishi mumkin.", status_code=403
            )
        serializer.save(product=product, user=user)
        services.refresh_rating(product)


@extend_schema(tags=["admin: reviews"])
class ReviewAdminViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Moderatsiya: yashirish (`is_published`) va do'kon javobi (`reply`). Rol: support, content_manager."""

    permission_classes = [HasRole.of("support", "content_manager")]
    serializer_class = AdminReviewSerializer
    pagination_class = AdminPagination
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        qs = Review.objects.select_related("user", "product").order_by("-created_at")
        if v := self.request.query_params.get("rating"):
            qs = qs.filter(rating=v)
        return qs

    def perform_update(self, serializer):
        review = serializer.save()
        services.refresh_rating(review.product)
