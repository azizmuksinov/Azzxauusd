import logging
import uuid

from apps.core.phone import mask_phone

from .base import SmsBackend, SmsResult

logger = logging.getLogger("sms.console")


class ConsoleSmsBackend(SmsBackend):
    """Dev/demo: SMS yuborilmaydi, faqat logga yoziladi. Bepul."""

    name = "console"

    def send(self, phone: str, text: str) -> SmsResult:
        logger.info("SMS -> %s: %s", mask_phone(phone), text)
        return SmsResult(provider=self.name, message_id=f"console-{uuid.uuid4().hex[:12]}")
