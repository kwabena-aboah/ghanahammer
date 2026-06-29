"""apps/gh_auctions/api_urls.py — REST API for auctions"""
from django.urls import path
from apps.gh_auctions.views import toggle_watchlist

urlpatterns = [
    path('<uuid:auction_id>/watch/', toggle_watchlist, name='api_toggle_watchlist'),
]
