"""apps/payments/tasks.py — Payment-related background tasks"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='release_mature_escrow')
def release_mature_escrow():
    """Auto-release escrow funds when auto_release_date has passed and buyer hasn't disputed."""
    from apps.payments.models import EscrowAccount

    now = timezone.now()
    mature = EscrowAccount.objects.filter(
        status=EscrowAccount.STATUS_HOLDING,
        auto_release_date__lte=now,
    ).select_related('seller', 'buyer', 'auction')

    released = 0
    for escrow in mature:
        try:
            escrow.release_to_seller()
            from apps.notifications.services import NotificationService
            NotificationService.create_in_app(
                escrow.seller,
                f'Escrow Released — {escrow.auction.lot_number}',
                f'GHS {escrow.amount_ghs:,.2f} has been released to your account.',
                'success',
                escrow.auction,
            )
            NotificationService.create_in_app(
                escrow.buyer,
                f'Escrow Auto-Released — {escrow.auction.lot_number}',
                f'Funds were auto-released to the seller after the holding period.',
                'info',
                escrow.auction,
            )
            released += 1
            logger.info(f'Escrow {escrow.id} auto-released to seller {escrow.seller.email}')
        except Exception as e:
            logger.exception(f'Error releasing escrow {escrow.id}: {e}')

    return f'Released {released} escrow accounts'
