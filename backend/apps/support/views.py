"""Chat API: mijoz tomoni (mehmon ham — token bilan) va xodim tomoni."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.admin_api import AdminPagination
from apps.core.exceptions import ApiError
from apps.core.permissions import HasRole

from . import services
from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "sender", "text", "products", "staff_name", "created_at"]

    def get_staff_name(self, obj) -> str:
        return (obj.staff.first_name or "Operator") if obj.staff_id else ""


class ChatStateSerializer(serializers.Serializer):
    token = serializers.CharField()
    status = serializers.CharField()
    messages = MessageSerializer(many=True)


class ChatSendSerializer(serializers.Serializer):
    token = serializers.CharField(required=False, allow_blank=True, max_length=48)
    text = serializers.CharField(max_length=services.MAX_TEXT, required=False, allow_blank=True)
    lang = serializers.CharField(required=False, allow_blank=True, max_length=8)
    handoff = serializers.BooleanField(required=False, default=False)


def _state(conv: Conversation, after: int = 0) -> dict:
    msgs = conv.messages.select_related("staff").filter(id__gt=after)
    return {"token": conv.token, "status": conv.status, "messages": MessageSerializer(msgs, many=True).data}


@extend_schema(tags=["chat"])
class ChatView(APIView):
    """Mijoz chati. Mehmon ham yoza oladi: suhbat `token` bilan ochiladi (brauzerda saqlanadi).

    GET ?token=&after= — yangi xabarlar (token yo'q/noto'g'ri bo'lsa — bo'sh suhbat).
    POST {token?, text, lang?} — xabar yuborish; AI darhol javob beradi yoki suhbat xodimga uzatiladi.
    POST {token, handoff: true} — operatorni chaqirish.
    """

    permission_classes = [AllowAny]
    # Mehmon tokeni eskirgan JWT bilan kelsa ham chat ishlasin: autentifikatsiya xatosi e'tiborga olinmaydi.
    authentication_classes: list = []

    def _user(self, request):
        from rest_framework_simplejwt.authentication import JWTAuthentication

        try:
            res = JWTAuthentication().authenticate(request)
        except Exception:  # noqa: BLE001 — yaroqsiz token: mehmon sifatida davom etadi
            return None
        return res[0] if res else None

    @extend_schema(responses=ChatStateSerializer)
    def get(self, request):
        token = request.query_params.get("token") or ""
        conv = Conversation.objects.filter(token=token).first() if token else None
        if conv is None:
            return Response({"token": "", "status": "ai", "messages": []})
        try:
            after = int(request.query_params.get("after") or 0)
        except ValueError:
            after = 0
        return Response(_state(conv, after))

    @extend_schema(request=ChatSendSerializer, responses=ChatStateSerializer)
    def post(self, request):
        ser = ChatSendSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        conv = services.get_or_create(d.get("token"), self._user(request), d.get("lang") or "uz")
        last = conv.messages.order_by("-id").values_list("id", flat=True).first() or 0
        if d.get("handoff"):
            services.handoff(conv)
        elif d.get("text", "").strip():
            services.customer_message(conv, d["text"])
        else:
            raise ApiError("empty_message", "Xabar bo'sh.")
        conv.refresh_from_db()
        return Response(_state(conv, last))


# --- xodim ---
class ConversationSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    last_text = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id", "status", "status_label", "customer", "phone", "lang", "unread_for_staff",
            "last_message_at", "last_text", "created_at",
        ]  # fmt: skip

    def get_last_text(self, obj) -> str:
        m = obj.messages.order_by("-id").first()
        return m.text[:120] if m else ""

    def get_customer(self, obj) -> str:
        return obj.name or (obj.user.first_name if obj.user_id and obj.user.first_name else "") or "Mehmon"


class ConversationDetailSerializer(ConversationSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = [*ConversationSerializer.Meta.fields, "messages"]


class StaffReplySerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000)


class ChatSummarySerializer(serializers.Serializer):
    waiting = serializers.IntegerField()
    unread = serializers.IntegerField()


class StaffStatusSerializer(serializers.Serializer):
    status = serializers.CharField(help_text="closed — yopish; ai — AI yordamchiga qaytarish")


@extend_schema(tags=["admin: chat"])
class ChatAdminViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Xodim: mijozlar suhbatlari. `?status=waiting` — javob kutayotganlar. Rol: support."""

    permission_classes = [HasRole.of("support", "content_manager")]
    pagination_class = AdminPagination

    def get_serializer_class(self):
        return ConversationSerializer if self.action == "list" else ConversationDetailSerializer

    def get_queryset(self):
        qs = Conversation.objects.select_related("user").exclude(last_message_at=None)
        status = self.request.query_params.get("status")
        if status == "open":
            qs = qs.filter(status__in=[Conversation.Status.WAITING, Conversation.Status.STAFF])
        elif status:
            qs = qs.filter(status=status)
        return qs.order_by("-unread_for_staff", "-last_message_at")

    def retrieve(self, request, *args, **kwargs):
        conv = self.get_object()
        services.mark_read(conv)
        conv.refresh_from_db()
        return Response(ConversationDetailSerializer(conv).data)

    @extend_schema(request=StaffReplySerializer, responses=ConversationDetailSerializer)
    @action(detail=True, methods=["post"])
    def reply(self, request, pk=None):
        ser = StaffReplySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        conv = self.get_object()
        services.staff_reply(conv, ser.validated_data["text"], user=request.user)
        return Response(ConversationDetailSerializer(get_object_or_404(Conversation, pk=conv.pk)).data)

    @extend_schema(request=StaffStatusSerializer, responses=ConversationDetailSerializer)
    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        ser = StaffStatusSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        conv = services.set_status(self.get_object(), ser.validated_data["status"])
        return Response(ConversationDetailSerializer(conv).data)

    @extend_schema(responses=ChatSummarySerializer)
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Chap menyudagi belgi uchun: javob kutayotgan suhbatlar soni."""
        waiting = Conversation.objects.filter(status=Conversation.Status.WAITING).count()
        unread = Conversation.objects.filter(status=Conversation.Status.STAFF, unread_for_staff__gt=0).count()
        return Response({"waiting": waiting, "unread": unread})
