"""apps/auctions/urls.py"""
from django.urls import path
from apps.gh_auctions import views

urlpatterns = [
    path('', views.home, name='home'),
    path('auctions/', views.auction_list, name='auction_list'),
    path('auctions/create/', views.auction_create, name='auction_create'),
    path('auctions/bulk-import/', views.bulk_import, name='bulk_import'),
    path('auctions/<slug:slug>/', views.auction_detail, name='auction_detail'),
    path('auctions/<slug:slug>/edit/', views.auction_edit, name='auction_edit'),
    path('auctions/<slug:slug>/question/', views.ask_question, name='auction_ask_question'),
    path('auctions/<uuid:auction_id>/watch/', views.toggle_watchlist, name='toggle_watchlist'),
]
