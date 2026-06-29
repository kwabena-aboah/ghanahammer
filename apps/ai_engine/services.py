"""
GhanaHammer AI Engine
Features: Price recommendation, description generator, demand forecasting, fraud detection
"""
import logging
import statistics
from decimal import Decimal
from django.db.models import Avg, Count, Max, Min
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
import json

logger = logging.getLogger(__name__)


class AIPriceRecommendationEngine:
    """
    Recommends starting bid, reserve price, and buy-now price
    based on historical auction data for the same category.
    """

    def recommend_prices(self, category_id, title, condition, location=None):
        """Return AI-suggested prices for a new listing."""
        from apps.gh_auctions.models import Auction

        # Pull historical sold auctions in same category
        historical = Auction.objects.filter(
            category_id=category_id,
            status__in=['sold'],
            winning_bid_amount__isnull=False,
        ).order_by('-created_at')[:200]

        if not historical.exists():
            return self._default_recommendation()

        amounts = [float(a.winning_bid_amount) for a in historical]
        avg_price = statistics.mean(amounts)
        median_price = statistics.median(amounts)
        std_dev = statistics.stdev(amounts) if len(amounts) > 1 else avg_price * 0.2

        # Adjust for condition
        condition_multipliers = {
            'new': 1.15,
            'refurbished': 0.90,
            'used': 0.75,
            'for_parts': 0.35,
        }
        multiplier = condition_multipliers.get(condition, 0.80)

        # Compute recommendations
        suggested_start = round(median_price * multiplier * 0.60, -1)   # 60% of adjusted median
        suggested_reserve = round(median_price * multiplier * 0.80, -1) # 80% of adjusted median
        suggested_buy_now = round(median_price * multiplier * 1.20, -1) # 20% above adjusted median

        # Demand score: how competitive is this category?
        avg_bids = historical.aggregate(avg=Avg('bid_count'))['avg'] or 1
        demand_score = min(1.0, avg_bids / 20.0)

        # Predict best auction duration
        if demand_score > 0.7:
            suggested_duration_days = 3
        elif demand_score > 0.4:
            suggested_duration_days = 5
        else:
            suggested_duration_days = 7

        return {
            'suggested_start_price': max(Decimal(str(suggested_start)), Decimal('10.00')),
            'suggested_reserve_price': max(Decimal(str(suggested_reserve)), Decimal('15.00')),
            'suggested_buy_now_price': max(Decimal(str(suggested_buy_now)), Decimal('20.00')),
            'demand_score': round(demand_score, 2),
            'suggested_duration_days': suggested_duration_days,
            'avg_winning_price': round(avg_price, 2),
            'median_winning_price': round(median_price, 2),
            'sample_size': len(amounts),
            'confidence': 'high' if len(amounts) >= 20 else ('medium' if len(amounts) >= 5 else 'low'),
        }

    def _default_recommendation(self):
        return {
            'suggested_start_price': Decimal('50.00'),
            'suggested_reserve_price': Decimal('80.00'),
            'suggested_buy_now_price': Decimal('150.00'),
            'demand_score': 0.3,
            'suggested_duration_days': 7,
            'avg_winning_price': None,
            'median_winning_price': None,
            'sample_size': 0,
            'confidence': 'none',
        }


class AIDescriptionGenerator:
    """
    Generates compelling auction descriptions from basic item details.
    Uses rule-based templates + category-aware language.
    In production, integrate Claude API for richer descriptions.
    """

    TEMPLATES = {
        'vehicles': (
            "Up for auction: {title}. This {condition} vehicle is a great opportunity "
            "for buyers seeking quality at a competitive price. {extra} "
            "Condition: {condition_display}. Location: {location}. "
            "All bids are final. Buyer is responsible for collection or shipping arrangements."
        ),
        'electronics': (
            "Listing: {title}. A {condition} {title} is available through this auction. "
            "{extra} Condition: {condition_display}. "
            "Tested and confirmed working (unless stated otherwise). Location: {location}."
        ),
        'real_estate': (
            "Property Auction: {title}. This is a rare opportunity to acquire a property through "
            "competitive bidding. {extra} All title documents will be transferred upon full payment. "
            "Location: {location}. Interested parties may request a site visit before bidding."
        ),
        'livestock': (
            "Livestock Auction: {title}. Healthy and well-maintained. {extra} "
            "Location: {location}. Buyer responsible for transport. "
            "All sales are final. No returns."
        ),
        'default': (
            "Auction Listing: {title}. {extra} Condition: {condition_display}. "
            "Location: {location}. This item is available to the highest bidder. "
            "Inspect photos carefully before bidding. All sales are final."
        ),
    }

    def generate(self, title, category_name, condition, location='Ghana', extra_notes=''):
        """Generate a product description."""
        cat_lower = category_name.lower()
        if 'vehicle' in cat_lower or 'car' in cat_lower or 'truck' in cat_lower:
            template_key = 'vehicles'
        elif 'electron' in cat_lower or 'phone' in cat_lower or 'computer' in cat_lower:
            template_key = 'electronics'
        elif 'property' in cat_lower or 'land' in cat_lower or 'estate' in cat_lower:
            template_key = 'real_estate'
        elif 'livestock' in cat_lower or 'animal' in cat_lower or 'poultry' in cat_lower:
            template_key = 'livestock'
        else:
            template_key = 'default'

        condition_labels = {
            'new': 'Brand New',
            'used': 'Used (Good Condition)',
            'refurbished': 'Professionally Refurbished',
            'for_parts': 'For Parts / As-Is',
        }

        description = self.TEMPLATES[template_key].format(
            title=title,
            condition=condition,
            condition_display=condition_labels.get(condition, condition.title()),
            location=location or 'Ghana',
            extra=extra_notes,
        )
        return description.strip()


class AIDemandForecaster:
    """Predict expected bids and final price for a new listing."""

    def forecast(self, category_id, starting_price, duration_days, condition):
        from apps.gh_auctions.models import Auction

        historical = Auction.objects.filter(
            category_id=category_id,
            status='sold',
        ).aggregate(
            avg_bids=Avg('bid_count'),
            avg_duration=Avg('bid_count'),
        )

        avg_bids = historical['avg_bids'] or 5
        price_f = float(starting_price)

        # Simple linear forecast
        expected_bids = max(1, int(avg_bids * (duration_days / 7)))
        expected_final = price_f * (1 + (expected_bids * 0.05))

        return {
            'expected_bid_count': expected_bids,
            'expected_final_price_ghs': round(expected_final, 2),
            'recommended_duration_days': 5 if expected_bids > 10 else 7,
            'demand_level': 'High' if expected_bids > 15 else ('Medium' if expected_bids > 7 else 'Low'),
        }


# ─── API Views ────────────────────────────────────────────────────────────────

price_engine = AIPriceRecommendationEngine()
description_engine = AIDescriptionGenerator()
forecaster = AIDemandForecaster()


@login_required
@require_POST
def api_price_recommendation(request):
    """POST {category_id, title, condition} → AI price suggestions"""
    try:
        body = json.loads(request.body)
        result = price_engine.recommend_prices(
            category_id=body.get('category_id'),
            title=body.get('title', ''),
            condition=body.get('condition', 'used'),
            location=body.get('location', ''),
        )
        # Serialize Decimals
        return JsonResponse({
            'success': True,
            'recommendations': {
                k: str(v) if isinstance(v, Decimal) else v
                for k, v in result.items()
            }
        })
    except Exception as e:
        logger.exception(f'Price recommendation error: {e}')
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_POST
def api_generate_description(request):
    """POST {title, category_name, condition, location, extra_notes} → description"""
    try:
        body = json.loads(request.body)
        description = description_engine.generate(
            title=body.get('title', ''),
            category_name=body.get('category_name', ''),
            condition=body.get('condition', 'used'),
            location=body.get('location', 'Ghana'),
            extra_notes=body.get('extra_notes', ''),
        )
        return JsonResponse({'success': True, 'description': description})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_POST
def api_demand_forecast(request):
    """POST {category_id, starting_price, duration_days, condition} → forecast"""
    try:
        body = json.loads(request.body)
        result = forecaster.forecast(
            category_id=body.get('category_id'),
            starting_price=body.get('starting_price', 100),
            duration_days=body.get('duration_days', 7),
            condition=body.get('condition', 'used'),
        )
        return JsonResponse({'success': True, 'forecast': result})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)
