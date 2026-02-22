import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_asgi_app = get_asgi_application()

from apps.notifications.middleware import TenantSchemaScopeMiddleware
from apps.notifications.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        'websocket': TenantSchemaScopeMiddleware(AuthMiddlewareStack(URLRouter(websocket_urlpatterns))),
    }
)
