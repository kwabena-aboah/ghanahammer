"""apps/analytics/tasks.py — Analytics background tasks"""
import logging
from celery import shared_task
from django.utils import timezone
from datetime import date

logger = logging.getLogger(__name__)


@shared_task(name='refresh_market_analytics')
def refresh_market_analytics():
    """Refresh pre-computed daily market analytics per category."""
    from apps.gh_auctions.models import Auction, Category
    from apps.analytics.models import MarketAnalytics
    from django.db.models import Avg, Count, Sum

    today = date.today()
    categories = Category.objects.filter(is_active=True)
    updated = 0

    for cat in categories:
        auctions = Auction.objects.filter(category=cat, created_at__date=today)
        sold = auctions.filter(status='sold', winning_bid_amount__isnull=False)

        agg = sold.aggregate(
            avg_price=Avg('winning_bid_amount'),
            avg_bids=Avg('bid_count'),
            volume=Sum('winning_bid_amount'),
        )

        MarketAnalytics.objects.update_or_create(
            date=today,
            category=cat,
            defaults={
                'total_auctions': auctions.count(),
                'total_sold': sold.count(),
                'avg_winning_price': agg['avg_price'] or 0,
                'avg_bids_per_auction': agg['avg_bids'] or 0,
                'total_volume_ghs': agg['volume'] or 0,
            }
        )
        updated += 1

    logger.info(f'Refreshed market analytics for {updated} categories on {today}')
    return f'Refreshed {updated} category analytics'
