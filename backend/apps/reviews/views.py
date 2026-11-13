from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.catalog.admin_api import AdminPagination
from apps.catalog.selectors import public_products
from apps.core.exceptions import ApiError
from apps.core.permissions import HasRole

from . import services
from .models import Question, Review


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


# ------------------------------------------------------------------ savol-javob
class QuestionSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ["id", "author", "text", "answer", "answered_at", "status", "created_at"]
        read_only_fields = ["id", "author", "answer", "answered_at", "status", "created_at"]

    def get_author(self, obj) -> str:
        return (obj.name or "").strip() or "Xaridor"


class QuestionCreateSerializer(serializers.Serializer):
    text = serializers.CharField(min_length=5, max_length=1000)
    name = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


@extend_schema(tags=["reviews"])
class ProductQuestionsView(generics.GenericAPIView):
    """Tovar bo'yicha savol-javob. Ro'yxatda faqat javob berilgan savollar (o'z savolingiz — javob kutayotgani
    ham). Savolni mehmon ham bera oladi; u xodim javob bergach saytda ko'rinadi."""

    permission_classes = [AllowAny]
    serializer_class = QuestionSerializer
    pagination_class = None

    def _product(self):
        return get_object_or_404(public_products(), slug=self.kwargs["slug"])

    @extend_schema(responses=QuestionSerializer(many=True))
    def get(self, request, slug):
        from django.db.models import Q

        cond = Q(status=Question.Status.ANSWERED)
        if request.user.is_authenticated:
            cond |= Q(status=Question.Status.NEW, user=request.user)
        qs = Question.objects.filter(cond, product=self._product())[:50]
        return Response(QuestionSerializer(qs, many=True).data)

    @extend_schema(request=QuestionCreateSerializer, responses={201: QuestionSerializer})
    def post(self, request, slug):
        from apps.accounts.otp import RateLimited, _incr_window
        from apps.accounts.views import client_ip

        ser = QuestionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ip = client_ip(request)
        if ip and _incr_window(f"question:ip:{ip}", 3600) > 10:
            raise RateLimited()
        user = request.user if request.user.is_authenticated else None
        name = ser.validated_data["name"].strip() or (user.first_name if user else "")
        q = Question.objects.create(
            product=self._product(), user=user, name=name[:80], text=ser.validated_data["text"].strip()
        )
        return Response(QuestionSerializer(q).data, status=201)


class QuestionSummarySerializer(serializers.Serializer):
    new = serializers.IntegerField()


class AdminQuestionSerializer(QuestionSerializer):
    product = serializers.SerializerMethodField()
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True, default="")

    class Meta(QuestionSerializer.Meta):
        fields = [*QuestionSerializer.Meta.fields, "product", "product_slug", "phone"]
        read_only_fields = [
            "id",
            "author",
            "text",
            "answered_at",
            "created_at",
            "product",
            "product_slug",
            "phone",
        ]

    def get_product(self, obj) -> str:
        return obj.product.name.get("uz") or obj.product.name.get("ru") or obj.product.slug


@extend_schema(tags=["admin: reviews"])
class QuestionAdminViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Savollar: javob yozish (`answer`) va yashirish (`status=hidden`). `status` bo'yicha filtr.
    Rol: support, content_manager."""

    permission_classes = [HasRole.of("support", "content_manager")]
    serializer_class = AdminQuestionSerializer
    pagination_class = AdminPagination
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        qs = Question.objects.select_related("product", "user")
        if v := self.request.query_params.get("status"):
            qs = qs.filter(status__in=v.split(","))
        return qs

    def perform_update(self, serializer):
        from django.utils import timezone

        data = serializer.validated_data
        extra = {}
        if "answer" in data:
            if data["answer"].strip():
                extra = {"answered_by": self.request.user, "answered_at": timezone.now()}
                if data.get("status", serializer.instance.status) != Question.Status.HIDDEN:
                    extra["status"] = Question.Status.ANSWERED
            elif data.get("status") != Question.Status.HIDDEN:
                extra = {"status": Question.Status.NEW, "answered_at": None, "answered_by": None}
        elif data.get("status") == Question.Status.ANSWERED and not serializer.instance.answer.strip():
            raise ApiError("validation_error", "Avval javob yozing.")
        serializer.save(**extra)

    @extend_schema(responses=QuestionSummarySerializer)
    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response({"new": Question.objects.filter(status=Question.Status.NEW).count()})
