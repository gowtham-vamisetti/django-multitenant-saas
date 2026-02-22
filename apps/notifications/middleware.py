from channels.db import database_sync_to_async

from .tenancy import host_from_scope, schema_name_from_host


class TenantSchemaScopeMiddleware:
    """
    Adds schema_name to websocket scope based on request host.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'websocket':
            host = host_from_scope(scope)
            scope['schema_name'] = await database_sync_to_async(schema_name_from_host)(host)
        return await self.app(scope, receive, send)
