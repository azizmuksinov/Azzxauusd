from dataclasses import dataclass
from functools import cache

from django.conf import settings
from django.utils.module_loading import import_string


class SmsError(Exception):
    """Provayder SMS'ni qabul qilmadi. `retryable` — qayta urinishning ma'nosi bormi."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class SmsResult:
    provider: str
    message_id: str = ""


class SmsBackend:
    name = "base"

    def send(self, phone: str, text: str) -> SmsResult:  # phone: +998XXXXXXXXX
        raise NotImplementedError


BACKENDS = {
    "console": "apps.notifications.sms.console.ConsoleSmsBackend",
    "eskiz": "apps.notifications.sms.eskiz.EskizSmsBackend",
}


@cache
def _backend_for(name: str) -> SmsBackend:
    if name not in BACKENDS:
        raise ValueError(f"Noma'lum SMS_BACKEND: {name}")
    return import_string(BACKENDS[name])()


def get_sms_backend() -> SmsBackend:
    return _backend_for(settings.SMS_BACKEND)
