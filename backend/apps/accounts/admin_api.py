"""Xodimlar va rollar: /api/v1/admin/staff (faqat admin).

Xodim telefon raqami bo'yicha qo'shiladi va unga login hamda parol beriladi — panelga faqat shular bilan
kiradi (SMS-kod xodimlar uchun ishlamaydi). Login/parolni faqat administrator beradi va almashtiradi.
Kuryerlar alohida (Kuryerlar bo'limida — kuryer profili bilan) yaratiladi, shu sababli bu yerda kuryer roli
berilmaydi; kuryerning login/paroli ham shu yerda beriladi.
"""

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.response import Response

from apps.core.exceptions import ApiError
from apps.core.permissions import HasRole

from . import staff_auth
from .models import Role, User
from .serializers import PhoneField

EDITABLE_ROLES = [r for r in Role.values if r != Role.COURIER]


class StaffSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "login",
            "has_password",
            "first_name",
            "last_name",
            "roles",
            "is_active",
            "last_login",
            "date_joined",
        ]

    def get_roles(self, obj) -> list[str]:
        return sorted(g.name for g in obj.groups.all())

    def get_has_password(self, obj) -> bool:
        return bool(obj.login) and obj.has_usable_password()


class StaffWriteSerializer(serializers.Serializer):
    phone = PhoneField(max_length=32, required=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    roles = serializers.ListField(child=serializers.ChoiceField(choices=EDITABLE_ROLES), allow_empty=True)
    login = serializers.CharField(max_length=32, required=False)
    password = serializers.CharField(max_length=128, required=False, trim_whitespace=False)
    is_active = serializers.BooleanField(required=False)


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
        # Yangi xodim login va parolsiz kira olmaydi — ikkalasi ham shu yerda beriladi.
        needs = bool(d["roles"]) and not (user.login and user.has_usable_password())
        if needs and not (d.get("login") or user.login):
            raise ApiError("validation_error", "Xodim uchun login kiriting.")
        if needs and not d.get("password"):
            raise ApiError("validation_error", "Xodim uchun parol kiriting.")
        if d.get("login") or d.get("password"):
            staff_auth.set_credentials(user, login=d.get("login"), password=d.get("password"))
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
        if "is_active" in d:
            if user == request.user and not d["is_active"]:
                raise ApiError("self_lockout", "O'zingizni bloklab bo'lmaydi.")
            user.is_active = d["is_active"]
        user.save()
        if "roles" in d:
            self._set_roles(user, d["roles"])
        if "login" in d or "password" in d:
            if "password" in d and not (d.get("login") or user.login):
                raise ApiError("validation_error", "Avval login bering.")
            staff_auth.set_credentials(user, login=d.get("login"), password=d.get("password"))
        if d.get("is_active") is False:
            staff_auth.revoke_sessions(user)
        return Response(StaffSerializer(User.objects.get(pk=user.pk)).data)
