"""Back-office API: /api/v1/admin/backoffice/...

Rollar: warehouse (hujjatlar), finance (kassa), admin (hammasi).
"""

from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.admin_api import AdminPagination
from apps.core.permissions import HasRole

from . import services
from .models import (
    CashAccount,
    CashTransaction,
    DocStatus,
    PurchaseReceipt,
    PurchaseReceiptLine,
    StockTransfer,
    StockTransferLine,
    Supplier,
    WriteOff,
    WriteOffLine,
)

WarehouseRole = HasRole.of("warehouse")
FinanceRole = HasRole.of("finance")
WarehouseOrFinance = HasRole.of("warehouse", "finance")


class SupplierSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "inn",
            "phone",
            "contact_person",
            "address",
            "bank_details",
            "note",
            "is_active",
            "balance",
        ]

    def validate_inn(self, v):
        if v and not (v.isdigit() and len(v) == 9):
            raise serializers.ValidationError("STIR 9 ta raqamdan iborat.")
        return v

    def get_balance(self, obj) -> dict:
        return {k: str(v) for k, v in services.supplier_balance(obj).items()}


class _DocSerializer(serializers.ModelSerializer):
    """Qatorlari bilan hujjat. Faqat qoralama tahrirlanadi; qatorlar to'liq almashtiriladi."""

    line_model = None
    line_fk = ""

    def validate(self, attrs):
        if self.instance and self.instance.status != DocStatus.DRAFT:
            raise serializers.ValidationError("O'tkazilgan hujjatni o'zgartirib bo'lmaydi.")
        return attrs

    @transaction.atomic
    def create(self, validated):
        lines = validated.pop("lines", [])
        doc = self.Meta.model.objects.create(**validated, created_by=self.context["request"].user)
        self._save_lines(doc, lines)
        return doc

    @transaction.atomic
    def update(self, instance, validated):
        lines = validated.pop("lines", None)
        instance = super().update(instance, validated)
        if lines is not None:
            instance.lines.all().delete()
            self._save_lines(instance, lines)
        return instance

    def _save_lines(self, doc, lines):
        self.line_model.objects.bulk_create([self.line_model(**{self.line_fk: doc}, **ln) for ln in lines])


class PurchaseReceiptLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseReceiptLine
        fields = ["id", "variant", "qty", "unit_cost", "serials"]

    def validate_serials(self, v):
        if not isinstance(v, list) or not all(isinstance(s, dict) for s in v):
            raise serializers.ValidationError(
                '[{"serial_number": "...", "imei1": "..."}] ko\'rinishida bering.'
            )
        allowed = {"serial_number", "imei1", "imei2"}
        if any(set(s) - allowed for s in v):
            raise serializers.ValidationError("Faqat serial_number, imei1, imei2 maydonlari.")
        return v


class PurchaseReceiptSerializer(_DocSerializer):
    line_model, line_fk = PurchaseReceiptLine, "receipt"
    lines = PurchaseReceiptLineSerializer(many=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseReceipt
        fields = [
            "id",
            "number",
            "status",
            "supplier",
            "warehouse",
            "supplier_doc_number",
            "supplier_doc_date",
            "comment",
            "lines",
            "total",
            "created_at",
            "posted_at",
        ]
        read_only_fields = ["number", "status", "posted_at"]

    def get_total(self, obj) -> str:
        return str(obj.total)


class TransferLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockTransferLine
        fields = ["id", "variant", "qty", "serial_ids"]


class TransferSerializer(_DocSerializer):
    line_model, line_fk = StockTransferLine, "transfer"
    lines = TransferLineSerializer(many=True)

    class Meta:
        model = StockTransfer
        fields = ["id", "number", "status", "source", "target", "comment", "lines", "created_at", "posted_at"]
        read_only_fields = ["number", "status", "posted_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        src = attrs.get("source", getattr(self.instance, "source", None))
        dst = attrs.get("target", getattr(self.instance, "target", None))
        if src and dst and src == dst:
            raise serializers.ValidationError({"target": "Manba va maqsad ombor bir xil bo'lmasin."})
        return attrs


class WriteOffLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = WriteOffLine
        fields = ["id", "variant", "qty", "serial_ids"]


class WriteOffSerializer(_DocSerializer):
    line_model, line_fk = WriteOffLine, "write_off"
    lines = WriteOffLineSerializer(many=True)

    class Meta:
        model = WriteOff
        fields = [
            "id",
            "number",
            "status",
            "warehouse",
            "reason",
            "supplier",
            "comment",
            "lines",
            "created_at",
            "posted_at",
        ]
        read_only_fields = ["number", "status", "posted_at"]


class _DocViewSet(viewsets.ModelViewSet):
    permission_classes = [WarehouseRole]
    pagination_class = AdminPagination
    http_method_names = ["get", "post", "patch", "head", "options"]  # o'chirish yo'q — bekor qilinadi

    def get_queryset(self):
        qs = self.serializer_class.Meta.model.objects.prefetch_related("lines")
        if v := self.request.query_params.get("status"):
            qs = qs.filter(status=v)
        return qs

    @extend_schema(request=None)
    @action(detail=True, methods=["post"], url_path="post", url_name="post")
    def post_document(self, request, pk=None):
        doc = self.post_fn(self.get_object(), request.user)
        return Response(self.get_serializer(doc).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        doc = services.cancel_draft(self.serializer_class.Meta.model, self.get_object())
        return Response(self.get_serializer(doc).data)


@extend_schema(tags=["admin: backoffice"])
class SupplierViewSet(viewsets.ModelViewSet):
    permission_classes = [WarehouseOrFinance]
    pagination_class = AdminPagination
    serializer_class = SupplierSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Supplier.objects.all()
        if q := self.request.query_params.get("q"):
            qs = qs.filter(name__icontains=q) | qs.filter(inn=q)
        return qs


@extend_schema(tags=["admin: backoffice"])
class ReceiptViewSet(_DocViewSet):
    serializer_class = PurchaseReceiptSerializer
    post_fn = staticmethod(services.post_receipt)


@extend_schema(tags=["admin: backoffice"])
class TransferViewSet(_DocViewSet):
    serializer_class = TransferSerializer
    post_fn = staticmethod(services.post_transfer)


@extend_schema(tags=["admin: backoffice"])
class WriteOffViewSet(_DocViewSet):
    serializer_class = WriteOffSerializer
    post_fn = staticmethod(services.post_write_off)


class CashAccountSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = CashAccount
        fields = ["id", "name", "kind", "is_active", "balance"]

    def get_balance(self, obj) -> str:
        return str(services.balance(obj))


class CashTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashTransaction
        fields = [
            "id",
            "account",
            "direction",
            "amount",
            "category",
            "supplier",
            "order",
            "reverses",
            "comment",
            "occurred_at",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["reverses", "created_by", "created_at"]
        extra_kwargs = {"occurred_at": {"required": False}}

    def create(self, validated):
        return services.record_cash(user=self.context["request"].user, **validated)


class ReverseSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=255)


@extend_schema(tags=["admin: backoffice"])
class CashAccountViewSet(viewsets.ModelViewSet):
    permission_classes = [FinanceRole]
    serializer_class = CashAccountSerializer
    pagination_class = None
    queryset = CashAccount.objects.all()
    http_method_names = ["get", "post", "patch", "head", "options"]


@extend_schema(tags=["admin: backoffice"])
class CashTransactionViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [FinanceRole]
    serializer_class = CashTransactionSerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = CashTransaction.objects.all()
        p = self.request.query_params
        for field in ("account", "category", "supplier", "direction"):
            if v := p.get(field):
                qs = qs.filter(**{field: v})
        if v := p.get("from"):
            qs = qs.filter(occurred_at__date__gte=v)
        if v := p.get("to"):
            qs = qs.filter(occurred_at__date__lte=v)
        return qs

    @extend_schema(request=ReverseSerializer, responses=CashTransactionSerializer)
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        ser = ReverseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tx = services.reverse_cash(self.get_object(), request.user, ser.validated_data["comment"])
        return Response(CashTransactionSerializer(tx).data, status=201)


@extend_schema(tags=["admin: backoffice"], responses={200: OpenApiTypes.OBJECT})
class StockValuationView(APIView):
    permission_classes = [WarehouseOrFinance]

    def get(self, request):
        return Response(services.stock_valuation())
