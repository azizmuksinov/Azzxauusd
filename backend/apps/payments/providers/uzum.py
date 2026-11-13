"""Uzum Bank Merchant API: Uzum bizning endpointlarimizga JSON so'rov yuboradi.

  POST /api/v1/webhooks/uzum/check    — buyurtma mavjudmi, to'lash mumkinmi
  POST /api/v1/webhooks/uzum/create   — tranzaksiya yaratish
  POST /api/v1/webhooks/uzum/confirm  — pul yechildi
  POST /api/v1/webhooks/uzum/reverse  — bekor qilish / qaytarish
  POST /api/v1/webhooks/uzum/status   — tranzaksiya holati

Autentifikatsiya: `Authorization: Basic base64(LOGIN:PASSWORD)` + `serviceId` tekshiruvi.
Summa tiyinda.

DIQQAT: maydon nomlari va xato kodlari Uzum Bank'ning ochiq ma'lumotlari asosida yozilgan; merchant akkaunti
va rasmiy hujjat olingach solishtiriladi (docs/04-savollar.md, S-14). Shu sababli kodlar bitta joyda.
"""

import base64
import hmac

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import ApiError
from apps.orders.models import Order

from .. import services
from ..models import Payment, Provider
from .payme import from_tiyin, now_ms, to_tiyin

ERR_ACCESS_DENIED = "10001"
ERR_JSON = "10002"
ERR_INVALID_OPERATION = "10003"
ERR_REQUIRED_PARAM = "10005"
ERR_INVALID_SERVICE = "10006"
ERR_ORDER_NOT_FOUND = "10007"
ERR_ALREADY_PAID = "10008"
ERR_WRONG_AMOUNT = "10009"
ERR_TXN_NOT_FOUND = "10014"
ERR_ALREADY_CANCELLED = "10015"
ERR_CANNOT_REVERSE = "10017"

ACCOUNT_KEY = "orderId"


def check_auth(header: str) -> bool:
    cfg = settings.UZUM
    if not cfg["LOGIN"] or not cfg["PASSWORD"] or not header.startswith("Basic "):
        return False
    try:
        login, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(login, cfg["LOGIN"]) and hmac.compare_digest(password, cfg["PASSWORD"])


def checkout_url(order: Order, amount, return_url: str = "") -> str | None:
    template = settings.UZUM["PAYMENT_URL_TEMPLATE"]
    if not template:
        return None
    return template.format(
        service_id=settings.UZUM["SERVICE_ID"],
        order=order.number,
        amount=to_tiyin(amount),
        return_url=return_url,
    )


STATUS_NAME = {
    Payment.Status.PENDING: "CREATED",
    Payment.Status.SUCCEEDED: "CONFIRMED",
    Payment.Status.CANCELLED: "REVERSED",
    Payment.Status.REFUNDED: "REVERSED",
}


class UzumError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class UzumHandler:
    def handle(self, operation: str, body: dict) -> dict:
        service_id = body.get("serviceId")
        try:
            if str(service_id) != str(settings.UZUM["SERVICE_ID"]):
                raise UzumError(ERR_INVALID_SERVICE)
            fn = {
                "check": self.check,
                "create": self.create,
                "confirm": self.confirm,
                "reverse": self.reverse,
                "status": self.status,
            }.get(operation)
            if fn is None:
                raise UzumError(ERR_INVALID_OPERATION)
            return {"serviceId": service_id, "timestamp": now_ms(), **fn(body)}
        except UzumError as exc:
            return {"serviceId": service_id, "timestamp": now_ms(), "status": "FAILED", "errorCode": exc.code}

    # --- yordamchilar ---
    @staticmethod
    def _order(body) -> Order:
        number = str((body.get("params") or {}).get(ACCOUNT_KEY, ""))
        order = Order.objects.filter(number=number).first()
        if order is None:
            raise UzumError(ERR_ORDER_NOT_FOUND)
        return order

    @staticmethod
    def _payable(order: Order, amount_tiyin=None) -> None:
        try:
            services.check_payable(order, from_tiyin(amount_tiyin) if amount_tiyin is not None else None)
        except services.NotPayable as exc:
            raise UzumError(
                ERR_ALREADY_PAID if services.amount_due(order) <= 0 else ERR_ORDER_NOT_FOUND
            ) from exc
        except ApiError as exc:
            raise UzumError(ERR_WRONG_AMOUNT) from exc

    @staticmethod
    def _txn(body) -> Payment:
        trans_id = body.get("transId")
        if not trans_id:
            raise UzumError(ERR_REQUIRED_PARAM)
        p = Payment.objects.filter(provider=Provider.UZUM, provider_txn_id=str(trans_id)).first()
        if p is None:
            raise UzumError(ERR_TXN_NOT_FOUND)
        return p

    # --- operatsiyalar ---
    def check(self, body) -> dict:
        order = self._order(body)
        self._payable(order)
        due = services.amount_due(order)
        return {
            "status": "OK",
            "data": {ACCOUNT_KEY: {"value": order.number}, "amount": {"value": to_tiyin(due)}},
        }

    def create(self, body) -> dict:
        trans_id, amount = body.get("transId"), body.get("amount")
        if not trans_id or amount is None:
            raise UzumError(ERR_REQUIRED_PARAM)
        existing = Payment.objects.filter(provider=Provider.UZUM, provider_txn_id=str(trans_id)).first()
        if existing is None:
            order = self._order(body)
            self._payable(order, amount)
            try:
                with transaction.atomic():
                    existing = Payment.objects.create(
                        order=order,
                        provider=Provider.UZUM,
                        provider_txn_id=str(trans_id),
                        amount=from_tiyin(amount),
                        provider_time=now_ms(),
                        raw={"create": body},
                    )
            except IntegrityError:
                existing = self._txn(body)
        return {
            "transId": existing.provider_txn_id,
            "status": STATUS_NAME[existing.status],
            "transTime": existing.provider_time,
            "amount": to_tiyin(existing.amount),
        }

    def confirm(self, body) -> dict:
        p = self._txn(body)
        if p.status in (Payment.Status.CANCELLED, Payment.Status.REFUNDED):
            raise UzumError(ERR_ALREADY_CANCELLED)
        try:
            p = services.mark_succeeded(p)
        except services.NotPayable as exc:
            raise UzumError(ERR_INVALID_OPERATION) from exc
        return {
            "transId": p.provider_txn_id,
            "status": "CONFIRMED",
            "confirmTime": int(p.performed_at.timestamp() * 1000),
            "amount": to_tiyin(p.amount),
        }

    def reverse(self, body) -> dict:
        p = self._txn(body)
        if p.status == Payment.Status.SUCCEEDED and not services.can_refund(p):
            raise UzumError(ERR_CANNOT_REVERSE)
        p = services.mark_cancelled(p)
        return {
            "transId": p.provider_txn_id,
            "status": "REVERSED",
            "reverseTime": int((p.cancelled_at or timezone.now()).timestamp() * 1000),
            "amount": to_tiyin(p.amount),
        }

    def status(self, body) -> dict:
        p = self._txn(body)
        return {"transId": p.provider_txn_id, "status": STATUS_NAME[p.status], "amount": to_tiyin(p.amount)}
