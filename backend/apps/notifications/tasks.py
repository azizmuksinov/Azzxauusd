from celery import shared_task

from .models import NotificationLog
from .sms import SmsError, get_sms_backend


@shared_task(bind=True, max_retries=3, default_retry_delay=5, acks_late=True)
def send_sms_task(self, log_id: int, text: str):
    log = NotificationLog.objects.get(pk=log_id)
    try:
        result = get_sms_backend().send(log.phone, text)
    except SmsError as exc:
        log.status = NotificationLog.Status.FAILED
        log.error = str(exc)
        log.save(update_fields=["status", "error", "updated_at"])
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=5 * (2**self.request.retries)) from exc
        return
    log.status = NotificationLog.Status.SENT
    log.provider = result.provider
    log.provider_message_id = result.message_id
    log.error = ""
    log.save(update_fields=["status", "provider", "provider_message_id", "error", "updated_at"])
