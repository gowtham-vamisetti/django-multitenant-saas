import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .services import build_user_notification_group
from .tenancy import host_from_scope, schema_name_from_host


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.close(code=4001)
            return

        schema_name = self.scope.get('schema_name')
        if not schema_name:
            host = host_from_scope(self.scope)
            schema_name = await database_sync_to_async(schema_name_from_host)(host)

        self.group_name = build_user_notification_group(schema_name, user.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notify(self, event):
        await self.send(text_data=json.dumps({'message': event['message'], 'created_at': event['created_at']}))
