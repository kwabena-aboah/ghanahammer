"""apps/bidding/api_urls.py — REST API endpoints for bidding"""
from django.urls import path
from apps.bidding.views import place_bid_api, set_auto_bid_api, buy_now_api

urlpatterns = [
    path('place/', place_bid_api, name='place_bid_api'),
    path('auto-bid/', set_auto_bid_api, name='set_auto_bid_api'),
    path('buy-now/', buy_now_api, name='buy_now_api'),
]
