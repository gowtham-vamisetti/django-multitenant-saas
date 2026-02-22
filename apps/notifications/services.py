import re

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import connection
from django.utils import timezone


def normalize_schema_name(schema_name: str) -> str:
    """Keep group names channel-layer-safe while preserving tenant identity."""
    raw = schema_name or 'public'
    return re.sub(r'[^A-Za-z0-9_.-]', '_', raw)


def build_user_notification_group(schema_name: str, user_id: int) -> str:
    return f'{normalize_schema_name(schema_name)}.user_notifications.{user_id}'


def push_user_notification(user_id: int, message: str, schema_name: str | None = None) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    active_schema = schema_name or getattr(connection, 'schema_name', 'public')
    group_name = build_user_notification_group(active_schema, user_id)
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'notify',
            'message': message,
            'created_at': timezone.now().isoformat(),
        },
    )
