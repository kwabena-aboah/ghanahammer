"""apps/bidding/views.py — REST fallback for WebSocket bidding"""
import json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from apps.bidding.services import BiddingService

service = BiddingService()


@login_required
@require_POST
def place_bid_api(request):
    data = json.loads(request.body)
    result = service.place_bid(
        auction_id=data.get('auction_id'),
        bidder=request.user,
        amount=data.get('amount'),
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )
    return JsonResponse(result)


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


@login_required
@require_POST
def buy_now_api(request):
    data = json.loads(request.body)
    result = service.process_buy_now(
        auction_id=data.get('auction_id'),
        buyer=request.user,
    )
    return JsonResponse(result)
