"""apps/notifications/urls.py"""
from django.urls import path
from apps.notifications import views

urlpatterns = [
    path('', views.notification_list, name='notification_list'),
    path('api/recent/', views.api_recent_notifications, name='api_recent_notifications'),
    path('mark-read/<uuid:pk>/', views.mark_read, name='mark_notification_read'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_notifications_read'),
]
