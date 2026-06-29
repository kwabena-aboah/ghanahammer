"""
GhanaHammer WebSocket Consumers
Real-time bidding, live auction updates
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)


class AuctionBiddingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for live auction bidding room.
    Each auction has its own group: auction_{auction_id}
    """

    async def connect(self):
        self.auction_id = self.scope['url_route']['kwargs']['auction_id']
        self.room_group_name = f'auction_{self.auction_id}'
        self.user = self.scope['user']

        # Join auction group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Send current auction state on connect
        auction_state = await self.get_auction_state()
        await self.send(text_data=json.dumps({
            'type': 'auction_state',
            'data': auction_state,
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get('type')

        if not self.user.is_authenticated:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Authentication required to bid.',
            }))
            return

        if msg_type == 'place_bid':
            await self.handle_place_bid(data)
        elif msg_type == 'set_auto_bid':
            await self.handle_set_auto_bid(data)
        elif msg_type == 'buy_now':
            await self.handle_buy_now(data)
        elif msg_type == 'heartbeat':
            await self.send(text_data=json.dumps({'type': 'pong'}))

    async def handle_place_bid(self, data):
        """Process a manual bid placement"""
        amount = data.get('amount')
        if not amount:
            await self.send(text_data=json.dumps({'type': 'error', 'message': 'Bid amount required.'}))
            return

        result = await self.place_bid(float(amount))
        if result['success']:
            # Broadcast to all in room
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'bid_placed',
                    'data': result['data'],
                }
            )
        else:
            await self.send(text_data=json.dumps({
                'type': 'bid_error',
                'message': result['message'],
            }))

    async def handle_set_auto_bid(self, data):
        """Set/update auto-bid maximum"""
        max_amount = data.get('max_amount')
        if not max_amount:
            return
        result = await self.set_auto_bid(float(max_amount))
        await self.send(text_data=json.dumps({
            'type': 'auto_bid_set',
            'success': result['success'],
            'message': result.get('message', ''),
        }))

    async def handle_buy_now(self, data):
        """Process Buy Now purchase"""
        result = await self.process_buy_now()
        if result['success']:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'auction_sold',
                    'data': result['data'],
                }
            )
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': result['message'],
            }))

    # Group message handlers (broadcast receivers)
    async def bid_placed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'bid_placed',
            'data': event['data'],
        }))

    async def auction_extended(self, event):
        await self.send(text_data=json.dumps({
            'type': 'auction_extended',
            'data': event['data'],
        }))

    async def auction_ended(self, event):
        await self.send(text_data=json.dumps({
            'type': 'auction_ended',
            'data': event['data'],
        }))

    async def auction_sold(self, event):
        await self.send(text_data=json.dumps({
            'type': 'auction_sold',
            'data': event['data'],
        }))

    async def live_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'live_update',
            'data': event['data'],
        }))

    # Database operations
    @database_sync_to_async
    def get_auction_state(self):
        from apps.gh_auctions.models import Auction
        try:
            auction = Auction.objects.get(id=self.auction_id)
            return {
                'id': str(auction.id),
                'lot_number': auction.lot_number,
                'title': auction.title,
                'current_price': str(auction.current_price),
                'bid_count': auction.bid_count,
                'status': auction.status,
                'end_time': auction.end_time.isoformat(),
                'time_remaining_seconds': max(0, (auction.end_time - timezone.now()).total_seconds()),
                'min_next_bid': str(auction.min_next_bid),
                'buy_now_price': str(auction.buy_now_price) if auction.buy_now_price else None,
                'reserve_met': auction.is_reserve_met,
            }
        except Exception as e:
            logger.error(f"Error fetching auction state: {e}")
            return {}

    @database_sync_to_async
    def place_bid(self, amount):
        from apps.bidding.services import BiddingService
        service = BiddingService()
        return service.place_bid(
            auction_id=self.auction_id,
            bidder=self.user,
            amount=amount,
            ip_address=self.scope.get('client', [None])[0],
        )

    @database_sync_to_async
    def set_auto_bid(self, max_amount):
        from apps.bidding.services import BiddingService
        service = BiddingService()
        return service.set_auto_bid(
            auction_id=self.auction_id,
            bidder=self.user,
            max_amount=max_amount,
        )

    @database_sync_to_async
    def process_buy_now(self):
        from apps.bidding.services import BiddingService
        service = BiddingService()
        return service.process_buy_now(
            auction_id=self.auction_id,
            buyer=self.user,
        )
