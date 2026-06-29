"""Celery configuration for GhanaHammer"""
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auction_platform.settings.production')

app = Celery('machneauction')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'close-expired-auctions': {
        'task': 'close_expired_auctions',
        'schedule': 60.0,
    },
    'activate-scheduled-auctions': {
        'task': 'activate_scheduled_auctions',
        'schedule': 60.0,
    },
    'activate-vip-previews': {
        'task': 'activate_vip_previews',
        'schedule': 60.0,
    },
    'process-auto-bids': {
        'task': 'process_auto_bids',
        'schedule': 30.0,
    },
    'send-ending-soon-alerts': {
        'task': 'send_ending_soon_alerts',
        'schedule': 600.0,
    },
    'refresh-analytics': {
        'task': 'refresh_market_analytics',
        'schedule': 86400.0,
    },
    'release-escrow': {
        'task': 'release_mature_escrow',
        'schedule': 3600.0,
    },
}
