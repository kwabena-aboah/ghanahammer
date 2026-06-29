"""apps/bidding/routing.py"""
from django.urls import re_path
from apps.bidding.consumers import AuctionBiddingConsumer

websocket_urlpatterns = [
    re_path(r'ws/auction/(?P<auction_id>[0-9a-f-]+)/$', AuctionBiddingConsumer.as_asgi()),
]
