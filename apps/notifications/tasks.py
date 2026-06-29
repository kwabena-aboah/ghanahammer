"""apps/notifications/tasks.py — Notification background tasks"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='send_ending_soon_alerts')
def send_ending_soon_alerts():
    """Send alerts to watchlist users for auctions ending within 1 hour."""
    from apps.gh_auctions.models import Auction, Watchlist
    from apps.notifications.services import NotificationService

    cutoff = timezone.now() + timezone.timedelta(hours=1)
    ending = Auction.objects.filter(
        status__in=['active', 'extended'],
        end_time__lte=cutoff,
        end_time__gt=timezone.now(),
    ).prefetch_related('watchers__user')

    sent = 0
    for auction in ending:
        for watch in auction.watchers.filter(alert_ending_soon=True).select_related('user'):
            try:
                NotificationService.notify_ending_soon(watch.user, auction)
                sent += 1
            except Exception as e:
                logger.exception(f'Error sending ending-soon alert: {e}')

    return f'Sent {sent} ending-soon alerts'
