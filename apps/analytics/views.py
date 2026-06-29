"""apps/analytics/views.py"""
import json
from decimal import Decimal
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from apps.analytics.models import SellerAnalyticsService, MarketAnalytics
from apps.gh_auctions.models import Category


def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


@login_required
def seller_analytics(request):
    if not request.user.has_analytics:
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.warning(request, 'Analytics are available on Silver plan and above.')
        return redirect('dashboard_subscription')

    days = int(request.GET.get('days', 30))
    service = SellerAnalyticsService()

    summary = service.get_summary(request.user, days)
    revenue_trend = service.get_revenue_trend(request.user, days)
    category_breakdown = service.get_category_breakdown(request.user)
    top_listings = service.get_top_performing_listings(request.user)
    bid_hours = service.get_bid_activity_by_hour(request.user)

    return render(request, 'dashboard/analytics.html', {
        'summary': summary,
        'revenue_trend': json.dumps(list(revenue_trend), default=decimal_default),
        'category_breakdown': json.dumps(list(category_breakdown), default=decimal_default),
        'top_listings': top_listings,
        'bid_hours': json.dumps(list(bid_hours), default=decimal_default),
    })


@login_required
def market_analytics(request):
    """Market trend data API"""
    category_slug = request.GET.get('category', '')
    days = int(request.GET.get('days', 30))

    data = MarketAnalytics.objects.all()
    if category_slug:
        data = data.filter(category__slug=category_slug)

    return JsonResponse({
        'data': list(data.values(
            'date', 'category__name',
            'avg_winning_price', 'avg_bids_per_auction',
            'total_sold', 'total_volume_ghs'
        )[:100])
    })
