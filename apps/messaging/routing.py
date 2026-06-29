"""apps/messaging/routing.py"""
from django.urls import re_path
from apps.messaging.consumers import DirectMessageConsumer

websocket_urlpatterns = [
    re_path(r'ws/messages/(?P<thread_id>[0-9a-f-]+)/$', DirectMessageConsumer.as_asgi()),
]
