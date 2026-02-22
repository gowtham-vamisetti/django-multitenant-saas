from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.notifications.models import Notification
from apps.notifications.services import push_user_notification

from .models import Product


@receiver(post_save, sender=Product)
def notify_staff_on_product_create(sender, instance: Product, created: bool, **kwargs):
    if not created:
        return

    User = get_user_model()
    for user in User.objects.filter(is_staff=True):
        Notification.objects.create(user=user, message=f'New product created: {instance.name}')
        push_user_notification(user.id, f'New product created: {instance.name}')
