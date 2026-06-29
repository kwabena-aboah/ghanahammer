"""apps/messaging/consumers.py — Real-time messaging WebSocket"""
import json
from decimal import Decimal
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class DirectMessageConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for direct messaging threads"""

    async def connect(self):
        self.thread_id = self.scope['url_route']['kwargs']['thread_id']
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close()
            return
        # Verify user is in thread
        if not await self.user_in_thread():
            await self.close()
            return
        self.group_name = f'thread_{self.thread_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('type') == 'send_message':
            msg = await self.save_message(data.get('content', ''), data.get('offer_amount'))
            await self.channel_layer.group_send(self.group_name, {
                'type': 'chat_message',
                'data': msg,
            })

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({'type': 'message', 'data': event['data']}))

    @database_sync_to_async
    def user_in_thread(self):
        return MessageThread.objects.filter(id=self.thread_id, participants=self.user).exists()

    @database_sync_to_async
    def save_message(self, content, offer_amount=None):
        thread = MessageThread.objects.get(id=self.thread_id)
        msg_type = Message.TYPE_OFFER if offer_amount else Message.TYPE_TEXT
        msg = Message.objects.create(
            thread=thread,
            sender=self.user,
            message_type=msg_type,
            content=content,
            offer_amount=Decimal(str(offer_amount)) if offer_amount else None,
        )
        thread.updated_at = msg.created_at
        thread.save(update_fields=['updated_at'])
        return {
            'id': str(msg.id),
            'sender': self.user.get_full_name() or self.user.username,
            'sender_id': str(self.user.id),
            'content': msg.content,
            'offer_amount': str(msg.offer_amount) if msg.offer_amount else None,
            'message_type': msg.message_type,
            'created_at': msg.created_at.isoformat(),
        }
