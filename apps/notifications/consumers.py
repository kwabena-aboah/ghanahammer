"""apps/notifications/consumers.py — WebSocket notification delivery"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class NotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time notification delivery"""

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close()
            return

        self.group_name = f'notifications_{self.user.id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send unread count on connect
        count = await self.get_unread_count()
        await self.send(text_data=json.dumps({
            'type': 'unread_count',
            'count': count,
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('type') == 'mark_read':
            notif_id = data.get('notification_id')
            if notif_id:
                await self.mark_read(notif_id)

    async def notification(self, event):
        """Receive notification from group and forward to WebSocket client"""
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'data': event['data'],
        }))

    @database_sync_to_async
    def get_unread_count(self):
        return Notification.objects.filter(user=self.user, is_read=False).count()

    @database_sync_to_async
    def mark_read(self, notif_id):
        Notification.objects.filter(id=notif_id, user=self.user).update(is_read=True)
