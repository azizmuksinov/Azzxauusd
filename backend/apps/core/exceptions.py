"""Yagona xato formati: {"error": {"code", "message", "fields"}}."""

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler as drf_exception_handler


class ApiError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"
    default_detail = "So'rov noto'g'ri."

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        status_code: int | None = None,
        extra: dict | None = None,
    ):
        super().__init__(detail=message or self.default_detail, code=code or self.default_code)
        self.error_code = code or self.default_code
        self.extra = extra or {}
        if status_code:
            self.status_code = status_code


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, ApiError):
        body = {"code": exc.error_code, "message": str(exc.detail), **exc.extra}
    elif isinstance(exc, ValidationError):
        fields = response.data if isinstance(response.data, dict) else {"non_field_errors": response.data}
        body = {"code": "validation_error", "message": "Ma'lumotlar noto'g'ri.", "fields": fields}
    else:
        detail = response.data.get("detail", "") if isinstance(response.data, dict) else response.data
        code = getattr(detail, "code", None) or getattr(exc, "default_code", "error")
        body = {"code": str(code), "message": str(detail)}

    response.data = {"error": body}
    return response
