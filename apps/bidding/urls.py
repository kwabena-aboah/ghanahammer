"""apps/bidding/urls.py"""
from django.urls import path
from apps.bidding import views as bidding_views

urlpatterns = [
    path('place/', bidding_views.place_bid_api, name='place_bid_api'),
    path('buy-now/', bidding_views.buy_now_api, name='buy_now_api'),
    path('auto-bid/', bidding_views.set_auto_bid_api, name='set_auto_bid_api'),
]
