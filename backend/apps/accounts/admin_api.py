"""Xodimlar va rollar: /api/v1/admin/staff (faqat admin).

Xodim telefon raqami bo'yicha qo'shiladi (parol shart emas — SMS kod bilan kiradi). Kuryerlar alohida
(Kuryerlar bo'limida — kuryer profili bilan) yaratiladi, shu sababli bu yerda kuryer roli berilmaydi.
"""

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.response import Response

from apps.core.exceptions import ApiError
from apps.core.permissions import HasRole

from .models import Role, User
from .serializers import PhoneField

EDITABLE_ROLES = [r for r in Role.values if r != Role.COURIER]


class StaffSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "phone", "first_name", "last_name", "roles", "last_login", "date_joined"]

    def get_roles(self, obj) -> list[str]:
        return sorted(g.name for g in obj.groups.all())


class StaffWriteSerializer(serializers.Serializer):
    phone = PhoneField(max_length=32, required=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    roles = serializers.ListField(child=serializers.ChoiceField(choices=EDITABLE_ROLES), allow_empty=True)


@extend_schema(tags=["admin: staff"])
class StaffViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Xodimlar ro'yxati (rolli foydalanuvchilar), qo'shish va rollarini o'zgartirish. `q` — telefon/ism."""

    permission_classes = [HasRole.of("admin")]
    serializer_class = StaffSerializer

    def get_queryset(self):
        qs = User.objects.prefetch_related("groups").order_by("-date_joined")
        q = self.request.query_params.get("q", "").strip()
        if q:
            digits = "".join(ch for ch in q if ch.isdigit())
            cond = Q(first_name__icontains=q) | Q(last_name__icontains=q)
            if digits:
                cond |= Q(phone__contains=digits)
            return qs.filter(cond)
        return qs.filter(Q(groups__isnull=False) | Q(is_superuser=True)).distinct()

    def _set_roles(self, user: User, roles: list[str]) -> None:
        if user == self.request.user and Role.ADMIN not in roles and not user.is_superuser:
            raise ApiError("self_lockout", "O'zingizdan admin rolini olib bo'lmaydi.")
        keep = list(user.groups.exclude(name__in=EDITABLE_ROLES))  # kuryer roli o'zgarmaydi
        groups = [Group.objects.get_or_create(name=r)[0] for r in roles]
        user.groups.set([*keep, *groups])

    @extend_schema(request=StaffWriteSerializer, responses={201: StaffSerializer})
    @transaction.atomic
    def create(self, request):
        ser = StaffWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if not d.get("phone"):
            raise ApiError("validation_error", "Telefon raqamni kiriting.")
        user = User.objects.filter(phone=d["phone"]).first() or User.objects.create_user(d["phone"])
        for f in ("first_name", "last_name"):
            if d.get(f):
                setattr(user, f, d[f])
        user.save()
        self._set_roles(user, d["roles"])
        return Response(StaffSerializer(user).data, status=201)

    @extend_schema(request=StaffWriteSerializer, responses=StaffSerializer)
    @transaction.atomic
    def partial_update(self, request, pk=None):
        user = self.get_object()
        ser = StaffWriteSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        for f in ("first_name", "last_name"):
            if f in d:
                setattr(user, f, d[f])
        user.save()
        if "roles" in d:
            self._set_roles(user, d["roles"])
        return Response(StaffSerializer(User.objects.get(pk=user.pk)).data)
