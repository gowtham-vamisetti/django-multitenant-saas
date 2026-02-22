from django.db import connection
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Product
from .services import ProductEventService


@receiver(post_save, sender=Product)
def notify_staff_on_product_create(sender, instance: Product, created: bool, **kwargs):
    ProductEventService(schema_name=connection.schema_name).handle_product_saved(instance, created)


@receiver(post_delete, sender=Product)
def cleanup_product_dependencies(sender, instance: Product, **kwargs):
    ProductEventService(schema_name=connection.schema_name).handle_product_deleted(instance.id)
