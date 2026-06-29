"""apps/analytics/urls.py"""
from django.urls import path
from apps.analytics import views

urlpatterns = [
    path('seller/', views.seller_analytics, name='seller_analytics'),
    path('market/', views.market_analytics, name='market_analytics'),
]
