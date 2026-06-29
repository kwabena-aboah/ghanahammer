"""
GhanaHammer Analytics
Seller dashboard, market trends, auction history analytics
"""
from django.db import models
from django.conf import settings
from django.db.models import Avg, Count, Sum, Max, Min, F, Q
from django.utils import timezone
from datetime import timedelta
import uuid


class AuctionView(models.Model):
    """Track unique auction page views for analytics"""
    auction = models.ForeignKey('gh_auctions.Auction', on_delete=models.CASCADE, related_name='view_records')
    viewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    referrer = models.CharField(max_length=500, blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gh_auction_views'
        indexes = [models.Index(fields=['auction', 'viewed_at'])]


class MarketAnalytics(models.Model):
    """Pre-computed daily market analytics per category"""
    date = models.DateField()
    category = models.ForeignKey('gh_auctions.Category', on_delete=models.CASCADE)
    total_auctions = models.PositiveIntegerField(default=0)
    total_sold = models.PositiveIntegerField(default=0)
    avg_winning_price = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    avg_bids_per_auction = models.FloatField(null=True)
    total_volume_ghs = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    class Meta:
        db_table = 'gh_market_analytics'
        unique_together = ['date', 'category']


class SellerAnalyticsService:
    """Compute seller-specific analytics for the dashboard"""

    def get_summary(self, seller, days=30):
        from apps.gh_auctions.models import Auction
        from apps.bidding.models import Bid

        since = timezone.now() - timedelta(days=days)
        auctions = Auction.objects.filter(seller=seller, created_at__gte=since)

        total_listings = auctions.count()
        active_listings = auctions.filter(status__in=['active', 'extended', 'preview']).count()
        sold = auctions.filter(status='sold')
        total_sold = sold.count()
        total_revenue = sold.aggregate(s=Sum('winning_bid_amount'))['s'] or 0
        avg_price = sold.aggregate(a=Avg('winning_bid_amount'))['a'] or 0
        total_views = auctions.aggregate(v=Sum('view_count'))['v'] or 0
        total_bids = auctions.aggregate(b=Sum('bid_count'))['b'] or 0
        total_watchers = auctions.aggregate(w=Sum('watchlist_count'))['w'] or 0
        conversion_rate = (total_sold / total_listings * 100) if total_listings else 0

        return {
            'period_days': days,
            'total_listings': total_listings,
            'active_listings': active_listings,
            'total_sold': total_sold,
            'total_revenue_ghs': float(total_revenue),
            'avg_winning_price_ghs': float(avg_price),
            'total_views': total_views,
            'total_bids': total_bids,
            'total_watchers': total_watchers,
            'conversion_rate': round(conversion_rate, 1),
        }

    def get_revenue_trend(self, seller, days=30):
        """Daily revenue for chart"""
        from apps.gh_auctions.models import Auction
        from django.db.models.functions import TruncDate

        data = (
            Auction.objects
            .filter(seller=seller, status='sold',
                    updated_at__gte=timezone.now() - timedelta(days=days))
            .annotate(date=TruncDate('updated_at'))
            .values('date')
            .annotate(revenue=Sum('winning_bid_amount'), count=Count('id'))
            .order_by('date')
        )
        return list(data)

    def get_category_breakdown(self, seller):
        """Revenue and count by category"""
        from apps.gh_auctions.models import Auction
        return list(
            Auction.objects
            .filter(seller=seller, status='sold')
            .values('category__name')
            .annotate(count=Count('id'), revenue=Sum('winning_bid_amount'))
            .order_by('-revenue')
        )

    def get_top_performing_listings(self, seller, limit=5):
        from apps.gh_auctions.models import Auction
        return list(
            Auction.objects
            .filter(seller=seller, status='sold')
            .order_by('-winning_bid_amount')
            .values('lot_number', 'title', 'winning_bid_amount', 'bid_count', 'view_count')
            [:limit]
        )

    def get_bid_activity_by_hour(self, seller, days=7):
        """Bid activity heatmap data (which hour of day gets most bids)"""
        from apps.bidding.models import Bid
        from django.db.models.functions import ExtractHour

        return list(
            Bid.objects
            .filter(
                auction__seller=seller,
                placed_at__gte=timezone.now() - timedelta(days=days)
            )
            .annotate(hour=ExtractHour('placed_at'))
            .values('hour')
            .annotate(count=Count('id'))
            .order_by('hour')
        )
