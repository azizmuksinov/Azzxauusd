from celery import shared_task

from .services import cleanup_guest_carts


@shared_task
def cleanup_guest_carts_task() -> int:
    return cleanup_guest_carts()
