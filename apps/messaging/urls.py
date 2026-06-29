"""apps/messaging/urls.py"""
from django.urls import path
from apps.messaging import views

urlpatterns = [
    path('', views.inbox, name='messaging_inbox'),
    path('start/<uuid:seller_id>/<uuid:auction_id>/', views.start_thread, name='messaging_start'),
    path('thread/<uuid:thread_id>/', views.thread_detail, name='messaging_thread'),
]
