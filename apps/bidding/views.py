"""apps/bidding/views.py — REST fallback for WebSocket bidding"""
import json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from apps.bidding.services import BiddingService

service = BiddingService()


@require_POST
def place_bid_api(request):
    try:
        data = json.loads(request.body or '{}')
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid bid request.'}, status=400)

    result = service.place_bid(
        auction_id=data.get('auction_id'),
        bidder=request.user if request.user.is_authenticated else None,
        amount=data.get('amount'),
        bidder_name=data.get('bidder_name', ''),
        bidder_email=data.get('bidder_email', ''),
        bidder_phone=data.get('bidder_phone', ''),
        pickup_notes=data.get('pickup_notes', ''),
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )
    # The service keeps the Bid instance for internal callers, but it cannot
    # be serialized in a JSON response.
    result.pop('bid', None)
    return JsonResponse(result, status=200 if result.get('success') else 400)


@login_required
@require_POST
def set_auto_bid_api(request):
    data = json.loads(request.body)
    result = service.set_auto_bid(
        auction_id=data.get('auction_id'),
        bidder=request.user,
        max_amount=data.get('max_amount'),
    )
    return JsonResponse(result)
