from celery import shared_task

from .services import cancel_unpaid_orders


@shared_task
def cancel_unpaid_orders_task() -> int:
    return cancel_unpaid_orders()
