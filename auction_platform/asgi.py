"""ASGI config for GhanaHammer — WebSocket + HTTP"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auction_platform.settings.production')

# MUST call get_asgi_application() before importing any Django models/views
from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

from apps.bidding.routing import websocket_urlpatterns as bidding_ws
from apps.messaging.routing import websocket_urlpatterns as messaging_ws
from apps.notifications.routing import websocket_urlpatterns as notification_ws

all_websocket_urlpatterns = bidding_ws + messaging_ws + notification_ws

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(all_websocket_urlpatterns)
        )
    ),
})
