"""apps/payments/tasks.py — Payment-related background tasks"""
import logging
from celery import shared_task
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='release_mature_escrow')
def release_mature_escrow():
    """Auto-release escrow funds when auto_release_date has passed and buyer hasn't disputed."""
    from apps.payments.models import EscrowAccount

    now = timezone.now()
    mature = EscrowAccount.objects.filter(
        status=EscrowAccount.STATUS_HOLDING,
    ).filter(
        Q(auto_release_date__lte=now) | Q(buyer_confirmed=True)
    ).filter(
        Q(payout_status=EscrowAccount.PAYOUT_NOT_STARTED)
        | Q(payout_status=EscrowAccount.PAYOUT_PENDING, paystack_transfer_code='')
        | Q(payout_status=EscrowAccount.PAYOUT_FAILED, paystack_transfer_code='')
    ).select_related('seller', 'buyer', 'auction', 'payment')

    released = 0
    pending = 0
    for escrow in mature:
        try:
            result = escrow.release_to_seller()
            if result['status'] == 'success':
                released += 1
            elif result['status'] == 'pending':
                pending += 1
            else:
                logger.warning('Escrow %s payout failed: %s', escrow.id, result['message'])
        except Exception as e:
            logger.exception(f'Error releasing escrow {escrow.id}: {e}')

    return f'Completed {released} payouts; {pending} payouts pending'
