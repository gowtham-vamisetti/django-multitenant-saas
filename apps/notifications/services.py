from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone


def push_user_notification(user_id: int, message: str) -> None:
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'user_notifications_{user_id}',
        {
            'type': 'notify',
            'message': message,
            'created_at': timezone.now().isoformat(),
        },
    )
