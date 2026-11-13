"""Click SHOP API: Click bizning `prepare` va `complete` endpointlarimizga form-POST yuboradi.

Imzo (MD5):
  prepare:  md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id + amount + action + sign_time)
  complete: md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id + merchant_prepare_id
                + amount + action + sign_time)
`merchant_trans_id` — buyurtma raqami. Summa so'mda (masalan "25000.00").
"""

import hashlib
import hmac
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.core.exceptions import ApiError
from apps.orders.models import Order

from .. import services
from ..models import Payment, Provider

OK = 0
ERR_SIGN = -1
ERR_AMOUNT = -2
ERR_ACTION = -3
ERR_ALREADY_PAID = -4
ERR_ORDER_NOT_FOUND = -5
ERR_TXN_NOT_FOUND = -6
ERR_UPDATE = -7
ERR_REQUEST = -8
ERR_CANCELLED = -9

ACTION_PREPARE, ACTION_COMPLETE = 0, 1
REQUIRED = [
    "click_trans_id",
    "service_id",
    "merchant_trans_id",
    "amount",
    "action",
    "sign_time",
    "sign_string",
]


def checkout_url(order: Order, amount: Decimal, return_url: str = "") -> str:
    cfg = settings.CLICK
    query = {
        "service_id": cfg["SERVICE_ID"],
        "merchant_id": cfg["MERCHANT_ID"],
        "amount": f"{amount:.2f}",
        "transaction_param": order.number,
    }
    if return_url:
        query["return_url"] = return_url
    return f"{cfg['CHECKOUT_URL']}?{urlencode(query)}"


def expected_sign(data: dict, action: int) -> str:
    secret = settings.CLICK["SECRET_KEY"]
    prepare_id = data.get("merchant_prepare_id", "") if action == ACTION_COMPLETE else ""
    raw = (
        f"{data['click_trans_id']}{data['service_id']}{secret}{data['merchant_trans_id']}"
        f"{prepare_id}{data['amount']}{data['action']}{data['sign_time']}"
    )
    return hashlib.md5(raw.encode()).hexdigest()  # noqa: S324 - Click protokoli MD5 talab qiladi


class ClickHandler:
    def handle(self, data: dict, action: int) -> tuple[dict, bool]:
        """Qaytaradi: (javob, imzo to'g'rimi)."""
        missing = [k for k in REQUIRED if k not in data] + (
            ["merchant_prepare_id"] if action == ACTION_COMPLETE and "merchant_prepare_id" not in data else []
        )
        if missing:
            return self._resp(data, ERR_REQUEST, f"Maydonlar yo'q: {', '.join(missing)}"), False
        if not settings.CLICK["SECRET_KEY"] or not hmac.compare_digest(
            str(data["sign_string"]).lower(), expected_sign(data, action)
        ):
            return self._resp(data, ERR_SIGN, "SIGN CHECK FAILED"), False
        if str(data["service_id"]) != str(settings.CLICK["SERVICE_ID"]):
            return self._resp(data, ERR_REQUEST, "service_id noto'g'ri"), True
        if str(data["action"]) != str(action):
            return self._resp(data, ERR_ACTION, "Action not found"), True
        try:
            amount = Decimal(str(data["amount"]))
        except InvalidOperation:
            return self._resp(data, ERR_REQUEST, "amount noto'g'ri"), True
        if action == ACTION_PREPARE:
            return self._prepare(data, amount), True
        return self._complete(data, amount), True

    @staticmethod
    def _resp(data: dict, error: int, note: str, **extra) -> dict:
        return {
            "click_trans_id": data.get("click_trans_id"),
            "merchant_trans_id": data.get("merchant_trans_id"),
            "error": error,
            "error_note": note,
            **extra,
        }

    def _prepare(self, data: dict, amount: Decimal) -> dict:
        order = Order.objects.filter(number=str(data["merchant_trans_id"])).first()
        if order is None:
            return self._resp(data, ERR_ORDER_NOT_FOUND, "Order not found")
        existing = Payment.objects.filter(
            provider=Provider.CLICK, provider_txn_id=str(data["click_trans_id"])
        ).first()
        if existing:
            if existing.status == Payment.Status.SUCCEEDED:
                return self._resp(data, ERR_ALREADY_PAID, "Already paid")
            if existing.status != Payment.Status.PENDING:
                return self._resp(data, ERR_CANCELLED, "Transaction cancelled")
            return self._resp(data, OK, "Success", merchant_prepare_id=existing.pk)
        try:
            services.check_payable(order, amount)
        except services.NotPayable as exc:
            code = ERR_ALREADY_PAID if services.amount_due(order) <= 0 else ERR_ORDER_NOT_FOUND
            return self._resp(data, code, str(exc.detail))
        except ApiError:
            return self._resp(data, ERR_AMOUNT, "Incorrect parameter amount")
        try:
            with transaction.atomic():
                p = Payment.objects.create(
                    order=order,
                    provider=Provider.CLICK,
                    provider_txn_id=str(data["click_trans_id"]),
                    amount=amount,
                    raw={"prepare": data},
                )
        except IntegrityError:
            p = Payment.objects.get(provider=Provider.CLICK, provider_txn_id=str(data["click_trans_id"]))
        return self._resp(data, OK, "Success", merchant_prepare_id=p.pk)

    def _complete(self, data: dict, amount: Decimal) -> dict:
        p = Payment.objects.filter(
            pk=_int(data["merchant_prepare_id"]),
            provider=Provider.CLICK,
            provider_txn_id=str(data["click_trans_id"]),
        ).first()
        if p is None:
            return self._resp(data, ERR_TXN_NOT_FOUND, "Transaction does not exist")
        if p.amount != amount:
            return self._resp(data, ERR_AMOUNT, "Incorrect parameter amount")
        if p.status == Payment.Status.SUCCEEDED:
            return self._resp(data, ERR_ALREADY_PAID, "Already paid", merchant_confirm_id=p.pk)
        if p.status != Payment.Status.PENDING:
            return self._resp(data, ERR_CANCELLED, "Transaction cancelled")
        # Click tomonida to'lov muvaffaqiyatsiz bo'lsa, `error` < 0 bilan keladi — bekor qilamiz.
        if _int(data.get("error", 0)) < 0:
            services.mark_cancelled(p)
            return self._resp(data, ERR_CANCELLED, "Transaction cancelled")
        try:
            services.mark_succeeded(p)
        except services.NotPayable:
            services.mark_cancelled(p)
            return self._resp(data, ERR_UPDATE, "Failed to update order")
        return self._resp(data, OK, "Success", merchant_confirm_id=p.pk)


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
