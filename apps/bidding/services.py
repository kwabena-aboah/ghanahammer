"""
GhanaHammer Bidding Service
Core bidding logic: manual bids, auto-bidding, sniper protection, fraud detection
"""
import logging
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.conf import settings

logger = logging.getLogger(__name__)


class BiddingService:
    """Central service for all bidding operations"""

    def place_bid(self, auction_id, bidder, amount, ip_address=None, user_agent=''):
        """
        Place a manual bid. Handles:
        - Validation
        - Bid sniper protection
        - Auto-bid counter-response
        - Fraud scoring
        - Notifications
        """
        from apps.gh_auctions.models import Auction
        from apps.bidding.models import Bid, AutoBid
        from apps.notifications.services import NotificationService

        try:
            with transaction.atomic():
                auction = Auction.objects.select_for_update().get(id=auction_id)
                amount = Decimal(str(amount))

                # Validations
                if not auction.is_active:
                    return {'success': False, 'message': 'This auction is not currently active.'}
                if auction.end_time <= timezone.now():
                    return {'success': False, 'message': 'This auction has ended.'}
                if auction.seller_id == bidder.id:
                    return {'success': False, 'message': 'You cannot bid on your own listing.'}
                if amount < auction.min_next_bid:
                    return {
                        'success': False,
                        'message': f'Minimum bid is GHS {auction.min_next_bid:,.2f}.',
                    }
                if auction.buy_now_price and amount >= auction.buy_now_price:
                    return {'success': False, 'message': f'Use Buy Now for GHS {auction.buy_now_price:,.2f}.'}

                # Fraud scoring
                fraud_score, fraud_flags = self._calculate_fraud_score(auction, bidder, amount, ip_address)
                if fraud_score >= 0.9:
                    self._create_fraud_flag(auction, bidder, fraud_flags)
                    return {'success': False, 'message': 'Bid could not be processed. Please contact support.'}

                # Outbid previous winning bidder
                previous_winning_bid = Bid.objects.filter(
                    auction=auction, status=Bid.STATUS_WINNING
                ).first()
                if previous_winning_bid:
                    previous_winning_bid.status = Bid.STATUS_OUTBID
                    previous_winning_bid.save(update_fields=['status'])

                # Create bid
                bid = Bid.objects.create(
                    auction=auction,
                    bidder=bidder,
                    amount=amount,
                    status=Bid.STATUS_WINNING,
                    source=Bid.SOURCE_MANUAL,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    fraud_score=fraud_score,
                    fraud_flags=fraud_flags,
                )

                # Update auction
                auction.current_price = amount
                auction.bid_count += 1
                if auction.reserve_price:
                    auction.reserve_met = amount >= auction.reserve_price

                # Bid sniper protection check
                sniper_extension = False
                threshold = timezone.timedelta(minutes=settings.AUCTION_SNIPER_THRESHOLD_MINUTES)
                if auction.end_time - timezone.now() < threshold:
                    auction.extend_for_sniper()
                    bid.triggered_extension = True
                    bid.save(update_fields=['triggered_extension'])
                    sniper_extension = True

                auction.save(update_fields=['current_price', 'bid_count', 'reserve_met'])

                # Notify previous bidder they were outbid
                if previous_winning_bid:
                    NotificationService.notify_outbid(
                        user=previous_winning_bid.bidder,
                        auction=auction,
                        new_amount=amount,
                    )

                # Trigger auto-bidder for other bidders
                self._trigger_auto_bids(auction, bidder, amount)

                # Update bidder stats
                bidder.total_bids += 1
                bidder.save(update_fields=['total_bids'])

                bid_data = {
                    'bid_id': str(bid.id),
                    'amount': str(amount),
                    'bidder': bidder.get_full_name() or bidder.username,
                    'bid_count': auction.bid_count,
                    'current_price': str(auction.current_price),
                    'end_time': auction.end_time.isoformat(),
                    'sniper_extension': sniper_extension,
                    'reserve_met': auction.reserve_met,
                    'min_next_bid': str(auction.min_next_bid),
                    'placed_at': bid.placed_at.isoformat(),
                }

                logger.info(f"Bid placed: GHS {amount} on {auction.lot_number} by {bidder.email}")
                return {'success': True, 'data': bid_data, 'bid': bid}

        except Exception as e:
            logger.exception(f"Error placing bid: {e}")
            return {'success': False, 'message': 'An error occurred. Please try again.'}

    def set_auto_bid(self, auction_id, bidder, max_amount):
        """Set or update auto-bid proxy maximum"""
        from apps.gh_auctions.models import Auction
        from apps.bidding.models import AutoBid

        try:
            auction = Auction.objects.get(id=auction_id)
            max_amount = Decimal(str(max_amount))

            if not auction.is_active:
                return {'success': False, 'message': 'Auction is not active.'}
            if auction.seller_id == bidder.id:
                return {'success': False, 'message': 'You cannot auto-bid on your own listing.'}
            if max_amount <= auction.current_price:
                return {
                    'success': False,
                    'message': f'Maximum must exceed current price of GHS {auction.current_price:,.2f}.',
                }

            auto_bid, created = AutoBid.objects.update_or_create(
                auction=auction, bidder=bidder,
                defaults={'max_amount': max_amount, 'status': AutoBid.STATUS_ACTIVE}
            )

            # Immediately bid if current price allows
            if auction.min_next_bid <= max_amount:
                self._execute_auto_bid(auction, auto_bid)

            return {'success': True, 'message': f'Auto-bid set to GHS {max_amount:,.2f}.'}

        except Exception as e:
            logger.exception(f"Error setting auto-bid: {e}")
            return {'success': False, 'message': 'Could not set auto-bid.'}

    def process_buy_now(self, auction_id, buyer):
        """Execute Buy Now purchase — instant win"""
        from apps.gh_auctions.models import Auction
        from apps.bidding.models import Bid
        from apps.notifications.services import NotificationService

        try:
            with transaction.atomic():
                auction = Auction.objects.select_for_update().get(id=auction_id)

                if not auction.buy_now_price:
                    return {'success': False, 'message': 'Buy Now is not available for this auction.'}
                if not auction.is_active:
                    return {'success': False, 'message': 'Auction is not active.'}
                if auction.seller_id == buyer.id:
                    return {'success': False, 'message': 'You cannot buy your own listing.'}

                amount = auction.buy_now_price

                # Create buy-now bid
                bid = Bid.objects.create(
                    auction=auction, bidder=buyer,
                    amount=amount, status=Bid.STATUS_WON,
                    source=Bid.SOURCE_BUY_NOW,
                )

                # Close auction immediately
                auction.status = Auction.STATUS_SOLD
                auction.winner = buyer
                auction.winning_bid_amount = amount
                auction.end_time = timezone.now()
                auction.save()

                NotificationService.notify_auction_won(buyer, auction, amount)
                NotificationService.notify_seller_sale(auction.seller, auction, amount)

                return {
                    'success': True,
                    'data': {
                        'auction_id': str(auction.id),
                        'amount': str(amount),
                        'winner': buyer.get_full_name(),
                    }
                }
        except Exception as e:
            logger.exception(f"Error processing buy now: {e}")
            return {'success': False, 'message': 'Buy Now could not be processed.'}

    def _trigger_auto_bids(self, auction, just_bid_user, current_amount):
        """Trigger auto-bids from other users when outbid"""
        from apps.bidding.models import AutoBid

        competing_auto_bids = AutoBid.objects.filter(
            auction=auction,
            status=AutoBid.STATUS_ACTIVE,
        ).exclude(bidder=just_bid_user).order_by('-max_amount')

        for auto_bid in competing_auto_bids:
            next_bid = current_amount + auction.bid_increment
            if auto_bid.max_amount >= next_bid:
                self._execute_auto_bid(auction, auto_bid)
                break
            else:
                auto_bid.status = AutoBid.STATUS_EXHAUSTED
                auto_bid.save(update_fields=['status'])
                from apps.notifications.services import NotificationService
                NotificationService.notify_auto_bid_exhausted(auto_bid.bidder, auction, auto_bid.max_amount)

    def _execute_auto_bid(self, auction, auto_bid):
        """Place auto-bid on behalf of user"""
        from apps.bidding.models import Bid
        from apps.notifications.services import NotificationService

        next_bid_amount = max(
            auction.min_next_bid,
            auction.current_price + auction.bid_increment
        )

        if next_bid_amount > auto_bid.max_amount:
            auto_bid.status = auto_bid.STATUS_EXHAUSTED
            auto_bid.save(update_fields=['status'])
            return

        with transaction.atomic():
            # Outbid existing winner
            Bid.objects.filter(auction=auction, status=Bid.STATUS_WINNING).update(
                status=Bid.STATUS_OUTBID
            )

            bid = Bid.objects.create(
                auction=auction,
                bidder=auto_bid.bidder,
                amount=next_bid_amount,
                status=Bid.STATUS_WINNING,
                source=Bid.SOURCE_AUTO,
            )

            auction.current_price = next_bid_amount
            auction.bid_count += 1
            if auction.reserve_price:
                auction.reserve_met = next_bid_amount >= auction.reserve_price
            auction.save(update_fields=['current_price', 'bid_count', 'reserve_met'])

            auto_bid.current_auto_bid = next_bid_amount
            auto_bid.save(update_fields=['current_auto_bid'])

            # Notify the auto-bidder they're still winning
            NotificationService.notify_auto_bid_placed(auto_bid.bidder, auction, next_bid_amount)

    def _calculate_fraud_score(self, auction, bidder, amount, ip_address):
        """Simple rule-based fraud scoring (supplement with AI)"""
        from apps.bidding.models import Bid
        from django.db.models import Count

        score = 0.0
        flags = []

        # Check bid velocity (too many bids in short time)
        recent_bids = Bid.objects.filter(
            bidder=bidder,
            placed_at__gte=timezone.now() - timezone.timedelta(minutes=5)
        ).count()
        if recent_bids > 20:
            score += 0.4
            flags.append('high_bid_velocity')

        # Check if same IP is bidding against self on this auction
        if ip_address:
            seller_ip_match = Bid.objects.filter(
                auction=auction,
                bidder=auction.seller,
                ip_address=ip_address
            ).exists()
            if seller_ip_match:
                score += 0.5
                flags.append('seller_same_ip')

        # Seller bidding (rare but check)
        if hasattr(auction, 'seller_id') and auction.seller_id == bidder.id:
            score = 1.0
            flags.append('self_bid')

        # Suspiciously round amounts on auctions
        if amount % 1000 == 0 and auction.bid_count < 3:
            score += 0.1
            flags.append('suspicious_round_amount')

        return min(score, 1.0), flags

    def _create_fraud_flag(self, auction, bidder, flags):
        from apps.bidding.models import FraudFlag
        for flag in flags:
            FraudFlag.objects.create(
                user=bidder,
                auction=auction,
                flag_type=flag if len(flag) <= 50 else 'suspicious_pattern',
                severity='high',
                details={'flags': flags},
            )
