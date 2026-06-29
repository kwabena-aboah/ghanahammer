"""apps/accounts/dashboard_urls.py — Dashboard views"""
from django.urls import path
from apps.gh_accounts import dashboard_views

urlpatterns = [
    path('', dashboard_views.dashboard_home, name='dashboard'),
    path('my-bids/', dashboard_views.my_bids, name='dashboard_my_bids'),
    path('my-auctions/', dashboard_views.my_auctions, name='dashboard_my_auctions'),
    path('watchlist/', dashboard_views.watchlist, name='dashboard_watchlist'),
    path('purchases/', dashboard_views.purchases, name='dashboard_purchases'),
    path('analytics/', dashboard_views.analytics_redirect, name='dashboard_analytics'),
    path('subscription/', dashboard_views.subscription_page, name='dashboard_subscription'),
    path('saved-searches/', dashboard_views.saved_searches, name='dashboard_saved_searches'),
    path('messages/', dashboard_views.messages_inbox, name='dashboard_messages'),
    path('settings/', dashboard_views.account_settings, name='dashboard_settings'),
]
