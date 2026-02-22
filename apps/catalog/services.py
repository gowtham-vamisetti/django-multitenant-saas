import logging

from django.contrib.auth import get_user_model

from apps.notifications.models import Notification
from apps.notifications.services import push_bulk_user_notification

from .cache import CatalogCacheService
from .models import Product
from .search import ProductSearchService

logger = logging.getLogger(__name__)


class ProductEventService:
    """
    Handles post-write side effects for products in a single place.
    """

    def __init__(self, schema_name: str | None) -> None:
        self.schema_name = schema_name or 'public'
        self.cache_service = CatalogCacheService(self.schema_name)
        self.search_service = ProductSearchService()

    def handle_product_saved(self, product: Product, created: bool) -> None:
        self.cache_service.invalidate_product_change(product.id)

        try:
            self.search_service.index_product(product)
        except Exception:
            logger.exception('Elasticsearch index failed for product %s', product.id)

        if created:
            self._notify_staff_about_product(product)

    def handle_product_deleted(self, product_id: int) -> None:
        self.cache_service.invalidate_product_change(product_id)

        try:
            self.search_service.delete_product(product_id)
        except Exception:
            logger.exception('Elasticsearch delete failed for product %s', product_id)

    def _notify_staff_about_product(self, product: Product) -> None:
        message = f'New product created: {product.name}'
        user_ids = self._staff_user_ids()
        if not user_ids:
            return

        Notification.objects.bulk_create([Notification(user_id=user_id, message=message) for user_id in user_ids])
        push_bulk_user_notification(user_ids, message, schema_name=self.schema_name)

    @staticmethod
    def _staff_user_ids() -> list[int]:
        User = get_user_model()
        return list(User.objects.filter(is_staff=True).values_list('id', flat=True))
