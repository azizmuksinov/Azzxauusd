import logging

from django.conf import settings

from .models import NotificationLog
from .tasks import send_sms_task

logger = logging.getLogger(__name__)


def send_sms(
    phone: str, text: str, *, template_code: str, user=None, log_body: str | None = None
) -> NotificationLog:
    """SMS'ni jurnalga yozib, yuborishni navbatga qo'yadi (yoki darhol yuboradi).

    `log_body` — bazaga yoziladigan matn (OTP kabi maxfiy matnlar uchun niqoblangan).
    """
    log = NotificationLog.objects.create(
        user=user,
        channel=NotificationLog.Channel.SMS,
        phone=phone,
        template_code=template_code,
        body=text if log_body is None else log_body,
        provider=settings.SMS_BACKEND,
    )
    if settings.SMS_ASYNC and not settings.CELERY_TASK_ALWAYS_EAGER:
        send_sms_task.delay(log.id, text)
    else:
        send_sms_task.apply(args=(log.id, text))
    return log
