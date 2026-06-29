"""apps/bidding/tasks.py — Bidding-related background tasks"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='process_auto_bids')
def process_auto_bids():
    """
    Periodic task: re-trigger auto-bids for auctions where the
    current winner is not covered by any auto-bid.
    """
    from apps.gh_auctions.models import Auction
    from apps.bidding.models import AutoBid
    from apps.bidding.services import BiddingService

    service = BiddingService()
    active_autos = AutoBid.objects.filter(
        status=AutoBid.STATUS_ACTIVE,
        auction__status__in=['active', 'extended'],
    ).select_related('auction', 'bidder').order_by('-max_amount')

    processed = 0
    for auto_bid in active_autos:
        try:
            auction = auto_bid.auction
            # Only fire if this auto-bidder isn't currently winning
            from apps.bidding.models import Bid
            current_winner = Bid.objects.filter(
                auction=auction, status=Bid.STATUS_WINNING
            ).first()
            if current_winner and current_winner.bidder != auto_bid.bidder:
                if auto_bid.max_amount >= auction.min_next_bid:
                    service._execute_auto_bid(auction, auto_bid)
                    processed += 1
        except Exception as e:
            logger.exception(f'Error processing auto-bid {auto_bid.id}: {e}')

    return f'Processed {processed} auto-bids'
