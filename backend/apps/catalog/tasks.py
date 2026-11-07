from celery import shared_task

from .models import Product
from .search import get_search_backend


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def index_products_task(product_ids: list[int]) -> None:
    backend = get_search_backend()
    products = list(Product.objects.filter(pk__in=product_ids).select_related("brand"))
    backend.index_products(products)
    missing = set(product_ids) - {p.pk for p in products}
    backend.delete_products(sorted(missing))


@shared_task
def run_import_task(job_id: int) -> None:
    from .importer import run_import_job
    from .models import ProductImport

    run_import_job(ProductImport.objects.get(pk=job_id))
