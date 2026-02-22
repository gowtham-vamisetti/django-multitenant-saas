import logging

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.notifications.models import Notification
from apps.notifications.services import push_user_notification

from .models import Product
from .search import ProductSearchService

logger = logging.getLogger(__name__)


def _cache_key(suffix: str) -> str:
    return f'{connection.schema_name}:catalog:{suffix}'


def _invalidate_product_cache(product_id: int) -> None:
    cache.delete(_cache_key('products:list'))
    cache.delete(_cache_key(f'products:{product_id}'))


@receiver(post_save, sender=Product)
def notify_staff_on_product_create(sender, instance: Product, created: bool, **kwargs):
    _invalidate_product_cache(instance.id)

    try:
        ProductSearchService().index_product(instance)
    except Exception:
        logger.exception('Elasticsearch index failed for product %s', instance.id)

    if not created:
        return

    User = get_user_model()
    for user in User.objects.filter(is_staff=True):
        Notification.objects.create(user=user, message=f'New product created: {instance.name}')
        push_user_notification(user.id, f'New product created: {instance.name}', schema_name=connection.schema_name)


@receiver(post_delete, sender=Product)
def cleanup_product_dependencies(sender, instance: Product, **kwargs):
    _invalidate_product_cache(instance.id)
    try:
        ProductSearchService().delete_product(instance.id)
    except Exception:
        logger.exception('Elasticsearch delete failed for product %s', instance.id)
