"""apps/messaging/models.py — In-app messaging and negotiation rooms"""
import uuid
import json
from django.db import models
from django.conf import settings
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class MessageThread(models.Model):
    """Conversation thread between buyer and seller about an auction"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='message_threads')
    auction = models.ForeignKey(
        'gh_auctions.Auction', on_delete=models.SET_NULL, null=True, blank=True
    )
    is_negotiation = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gh_message_threads'
        ordering = ['-updated_at']


class Message(models.Model):
    """Single message within a thread"""
    TYPE_TEXT = 'text'
    TYPE_OFFER = 'offer'       # Negotiation offer
    TYPE_SYSTEM = 'system'
    TYPE_CHOICES = [
        (TYPE_TEXT, 'Text'),
        (TYPE_OFFER, 'Price Offer'),
        (TYPE_SYSTEM, 'System'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(MessageThread, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages'
    )
    message_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_TEXT)
    content = models.TextField()
    offer_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    offer_accepted = models.BooleanField(null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gh_messages'
        ordering = ['created_at']
