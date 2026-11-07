"""Payme Merchant API (JSON-RPC 2.0). Hujjat: https://developer.help.paycom.uz

Payme bizning `/api/v1/webhooks/payme` ga so'rov yuboradi:
CheckPerformTransaction, CreateTransaction, PerformTransaction, CancelTransaction,
CheckTransaction, GetStatement.

- Autentifikatsiya: `Authorization: Basic base64("Paycom:<KEY>")` — har so'rovda tekshiriladi.
- Summa tiyinda keladi (1 so'm = 100 tiyin).
- HTTP status har doim 200; xato JSON-RPC `error` ichida.
- Tranzaksiya 12 soat ichida bajarilmasa — bekor qilinadi (reason=4).
"""

import base64
import hmac
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import ApiError
from apps.orders.models import Order

from .. import services
from ..models import Payment, Provider

TIMEOUT_MS = 12 * 3600 * 1000

# Payme xato kodlari
ERR_TRANSPORT = -32300
ERR_PARSE = -32700
ERR_METHOD = -32601
ERR_AUTH = -32504
ERR_WRONG_AMOUNT = -31001
ERR_TXN_NOT_FOUND = -31003
ERR_CANNOT_CANCEL = -31007
ERR_CANNOT_PERFORM = -31008
ERR_ORDER_NOT_FOUND = -31050
ERR_ORDER_BUSY = -31051  # buyurtma uchun boshqa faol tranzaksiya bor
ERR_ORDER_NOT_PAYABLE = -31052

STATE_CREATED, STATE_DONE, STATE_CANCELLED, STATE_REFUNDED = 1, 2, -1, -2


class PaymeError(Exception):
    def __init__(self, code: int, message: str, data: str | None = None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data

    def as_dict(self):
        err = {"code": self.code, "message": {"uz": self.message, "ru": self.message, "en": self.message}}
        if self.data:
            err["data"] = self.data
        return err


def to_tiyin(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


def from_tiyin(value) -> Decimal:
    return (Decimal(int(value)) / 100).quantize(Decimal("0.01"))


def now_ms() -> int:
    return int(timezone.now().timestamp() * 1000)


def _ms(dt) -> int:
    return int(dt.timestamp() * 1000) if dt else 0


def check_auth(header: str) -> bool:
    key = settings.PAYME["KEY"]
    if not key or not header.startswith("Basic "):
        return False
    try:
        login, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    return login == "Paycom" and hmac.compare_digest(password, key)


def checkout_url(order: Order, amount: Decimal, return_url: str = "") -> str:
    """Xaridorni Payme sahifasiga yuborish havolasi."""
    cfg = settings.PAYME
    params = f"m={cfg['MERCHANT_ID']};ac.{cfg['ACCOUNT_FIELD']}={order.number};a={to_tiyin(amount)}"
    if return_url:
        params += f";c={return_url}"
    return f"{cfg['CHECKOUT_URL'].rstrip('/')}/{base64.b64encode(params.encode()).decode()}"


def _receipt_detail(order: Order, amount: Decimal) -> dict:
    """Fiskal chek ma'lumotlari (Payme OFD'ga yuboradi): MXIK, qadoq kodi, QQS."""
    items = [
        {
            "title": (i.product_name.get("uz") or i.sku)[:128],
            "price": to_tiyin(i.unit_price),
            "count": i.qty,
            "code": i.mxik_code,
            "package_code": settings.PAYME["DEFAULT_PACKAGE_CODE"],
            "vat_percent": int(i.vat_percent),
        }
        for i in order.items.all()
    ]
    if order.delivery_fee:
        items.append(
            {
                "title": "Yetkazib berish",
                "price": to_tiyin(order.delivery_fee + order.lifting_fee),
                "count": 1,
                "code": settings.PAYME["DELIVERY_MXIK"],
                "package_code": settings.PAYME["DELIVERY_PACKAGE_CODE"],
                "vat_percent": settings.PAYME["DELIVERY_VAT"],
            }
        )
    if amount != order.total:
        # Qisman (avans) to'lov: chekda faqat to'lanayotgan qism (OFD qoidalari — S-15 da tasdiqlanadi).
        delivery_total = order.delivery_fee + order.lifting_fee
        if order.delivery_fee and amount == delivery_total:
            items = [items[-1]]
        else:
            items = [{**items[0], "title": "Avans to'lov", "price": to_tiyin(amount), "count": 1}]
    return {"receipt_type": 0, "items": items}


class PaymeHandler:
    def handle(self, body: dict) -> dict:
        req_id = body.get("id")
        method = body.get("method")
        params = body.get("params") or {}
        handler = {
            "CheckPerformTransaction": self.check_perform,
            "CreateTransaction": self.create,
            "PerformTransaction": self.perform,
            "CancelTransaction": self.cancel,
            "CheckTransaction": self.check,
            "GetStatement": self.statement,
        }.get(method)
        try:
            if handler is None:
                raise PaymeError(ERR_METHOD, "Metod topilmadi", method)
            return {"jsonrpc": "2.0", "id": req_id, "result": handler(params)}
        except PaymeError as exc:
            return {"jsonrpc": "2.0", "id": req_id, "error": exc.as_dict()}

    # --- yordamchilar ---
    def _order(self, params) -> Order:
        account = params.get("account") or {}
        number = str(account.get(settings.PAYME["ACCOUNT_FIELD"], ""))
        order = Order.objects.filter(number=number).first()
        if order is None:
            raise PaymeError(ERR_ORDER_NOT_FOUND, "Buyurtma topilmadi", settings.PAYME["ACCOUNT_FIELD"])
        return order

    def _validate(self, order: Order, amount_tiyin) -> None:
        try:
            services.check_payable(order, from_tiyin(amount_tiyin))
        except services.NotPayable as exc:
            raise PaymeError(ERR_ORDER_NOT_PAYABLE, str(exc.detail), settings.PAYME["ACCOUNT_FIELD"]) from exc
        except ApiError as exc:
            raise PaymeError(ERR_WRONG_AMOUNT, str(exc.detail)) from exc

    def _txn(self, txn_id) -> Payment:
        p = Payment.objects.filter(provider=Provider.PAYME, provider_txn_id=str(txn_id)).first()
        if p is None:
            raise PaymeError(ERR_TXN_NOT_FOUND, "Tranzaksiya topilmadi")
        return p

    @staticmethod
    def _state(p: Payment) -> int:
        return {
            Payment.Status.PENDING: STATE_CREATED,
            Payment.Status.SUCCEEDED: STATE_DONE,
            Payment.Status.CANCELLED: STATE_CANCELLED,
            Payment.Status.REFUNDED: STATE_REFUNDED,
        }[p.status]

    def _txn_view(self, p: Payment) -> dict:
        return {
            "create_time": p.provider_time,
            "perform_time": _ms(p.performed_at),
            "cancel_time": _ms(p.cancelled_at),
            "transaction": str(p.pk),
            "state": self._state(p),
            "reason": p.cancel_reason,
        }

    def _expired(self, p: Payment) -> bool:
        return p.provider_time is not None and now_ms() - p.provider_time > TIMEOUT_MS

    # --- metodlar ---
    def check_perform(self, params) -> dict:
        order = self._order(params)
        self._validate(order, params.get("amount"))
        if order.payments.filter(provider=Provider.PAYME, status=Payment.Status.PENDING).exists():
            raise PaymeError(ERR_ORDER_BUSY, "Buyurtma uchun boshqa to'lov jarayonda")
        return {"allow": True, "detail": _receipt_detail(order, from_tiyin(params["amount"]))}

    def create(self, params) -> dict:
        txn_id = str(params.get("id"))
        existing = Payment.objects.filter(provider=Provider.PAYME, provider_txn_id=txn_id).first()
        if existing:
            if existing.status != Payment.Status.PENDING:
                raise PaymeError(ERR_CANNOT_PERFORM, "Tranzaksiya faol emas")
            if self._expired(existing):
                services.mark_cancelled(existing, reason=4)
                raise PaymeError(ERR_CANNOT_PERFORM, "Tranzaksiya muddati o'tgan")
            return {
                "create_time": existing.provider_time,
                "transaction": str(existing.pk),
                "state": STATE_CREATED,
            }

        order = self._order(params)
        self._validate(order, params.get("amount"))
        if order.payments.filter(provider=Provider.PAYME, status=Payment.Status.PENDING).exists():
            raise PaymeError(ERR_ORDER_BUSY, "Buyurtma uchun boshqa to'lov jarayonda")
        provider_time = int(params.get("time") or now_ms())
        if now_ms() - provider_time > TIMEOUT_MS:
            raise PaymeError(ERR_CANNOT_PERFORM, "Tranzaksiya vaqti eskirgan")
        try:
            with transaction.atomic():
                p = Payment.objects.create(
                    order=order,
                    provider=Provider.PAYME,
                    provider_txn_id=txn_id,
                    amount=from_tiyin(params["amount"]),
                    provider_time=provider_time,
                    raw={"create": params},
                )
        except IntegrityError:
            p = self._txn(txn_id)
        return {"create_time": p.provider_time, "transaction": str(p.pk), "state": STATE_CREATED}

    def perform(self, params) -> dict:
        p = self._txn(params.get("id"))
        if p.status == Payment.Status.SUCCEEDED:
            return {"transaction": str(p.pk), "perform_time": _ms(p.performed_at), "state": STATE_DONE}
        if p.status != Payment.Status.PENDING:
            raise PaymeError(ERR_CANNOT_PERFORM, "Tranzaksiya bekor qilingan")
        if self._expired(p):
            services.mark_cancelled(p, reason=4)
            raise PaymeError(ERR_CANNOT_PERFORM, "Tranzaksiya muddati o'tgan")
        try:
            p = services.mark_succeeded(p)
        except services.NotPayable as exc:
            raise PaymeError(ERR_CANNOT_PERFORM, str(exc.detail)) from exc
        return {"transaction": str(p.pk), "perform_time": _ms(p.performed_at), "state": STATE_DONE}

    def cancel(self, params) -> dict:
        p = self._txn(params.get("id"))
        if p.status == Payment.Status.SUCCEEDED and not services.can_refund(p):
            raise PaymeError(ERR_CANNOT_CANCEL, "Buyurtma jo'natilgan — bekor qilib bo'lmaydi")
        p = services.mark_cancelled(p, reason=params.get("reason"))
        return {"transaction": str(p.pk), "cancel_time": _ms(p.cancelled_at), "state": self._state(p)}

    def check(self, params) -> dict:
        return self._txn_view(self._txn(params.get("id")))

    def statement(self, params) -> dict:
        start = datetime.fromtimestamp(int(params.get("from", 0)) / 1000, tz=UTC)
        end = datetime.fromtimestamp(int(params.get("to", now_ms())) / 1000, tz=UTC) + timedelta(
            milliseconds=1
        )
        start_ms, end_ms = _ms(start), _ms(end)
        rows = Payment.objects.filter(
            provider=Provider.PAYME, provider_time__gte=start_ms, provider_time__lt=end_ms
        ).select_related("order")
        return {
            "transactions": [
                {
                    "id": p.provider_txn_id,
                    "time": p.provider_time,
                    "amount": to_tiyin(p.amount),
                    "account": {settings.PAYME["ACCOUNT_FIELD"]: p.order.number},
                    **self._txn_view(p),
                }
                for p in rows.order_by("provider_time")
            ]
        }
