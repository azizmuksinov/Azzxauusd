from celery import shared_task

from .services import release_expired


@shared_task
def release_expired_reservations() -> int:
    return release_expired()
