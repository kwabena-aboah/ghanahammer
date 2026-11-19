"""GhanaHammer Payment Views"""
import json
import logging
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.utils.crypto import constant_time_compare

from apps.payments.models import Payment, EscrowAccount, BankTransferInstruction, PaystackWebhookLog
from apps.payments.paystack_service import PaystackService
from apps.gh_auctions.models import Auction

logger = logging.getLogger(__name__)
paystack = PaystackService()


@require_GET
def release_mature_escrow_cron(request):
    """Run scheduled escrow releases from Vercel Cron using a shared secret."""
    if not settings.VERCEL_CRON_ENABLED:
        return JsonResponse({'disabled': True})

    if not settings.CRON_SECRET:
        logger.error('CRON_SECRET is not configured; refusing scheduled payout execution.')
        return JsonResponse({'error': 'Scheduled payouts are not configured.'}, status=503)

    expected_authorization = f'Bearer {settings.CRON_SECRET}'
    if not constant_time_compare(
        request.headers.get('Authorization', ''), expected_authorization
    ):
        return HttpResponse(status=401)

    from apps.payments.tasks import release_mature_escrow
    try:
        result = release_mature_escrow()
    except Exception:
        logger.exception('Scheduled escrow payout run failed.')
        return JsonResponse({'error': 'Scheduled payout run failed.'}, status=500)
    return JsonResponse({'result': result})


@login_required
def checkout(request, auction_id):
    """Checkout page for auction win payment"""
    auction = get_object_or_404(Auction, id=auction_id)

    # Ensure user is the winner
    if auction.winner != request.user:
        messages.error(request, 'You are not the winner of this auction.')
        return redirect('auction_detail', slug=auction.slug)

    if auction.status != Auction.STATUS_SOLD or auction.winning_bid_amount is None:
        messages.error(request, 'Payment is available after the auction has been finalized.')
        return redirect('dashboard_purchases')

    # Check for existing pending payment
    existing = Payment.objects.filter(
        user=request.user, auction=auction,
        payment_type=Payment.TYPE_BID_WIN,
        status=Payment.STATUS_SUCCESS,
    ).first()
    if existing:
        messages.info(request, 'You have already paid for this auction.')
        return redirect('dashboard_purchases')

    amount = auction.winning_bid_amount

    if request.method == 'POST':
        channel_type = request.POST.get('channel_type', 'card')
        momo_number = request.POST.get('momo_number', '')
        momo_network = request.POST.get('momo_network', '')

        payment = Payment.objects.create(
            user=request.user,
            auction=auction,
            payment_type=Payment.TYPE_BID_WIN,
            amount_ghs=amount,
            channel=channel_type,
            momo_number=momo_number,
            momo_network=momo_network,
        )

        callback_url = request.build_absolute_uri(reverse('payment_callback'))

        if channel_type == 'mobile_money' and momo_number:
            result = paystack.charge_mobile_money(payment)
            if result['success'] and result.get('requires_action'):
                request.session['pending_momo_reference'] = payment.paystack_reference
                messages.info(request, str(result.get('message') or 'Approve payment on your phone.'))
                return render(request, 'payments/momo_otp.html', {'payment': payment})
            if result['success']:
                verified = paystack.verify_transaction(payment.paystack_reference)
                if verified['success'] and paystack.complete_payment(payment, verified['data']):
                    messages.success(request, 'Payment confirmed and held in escrow.')
                    return redirect('dashboard_purchases')
                result = {'success': False, 'message': 'Payment could not be verified.'}
        elif channel_type == 'bank_transfer':
            result = paystack.create_dedicated_virtual_account(payment)
            if result['success']:
                BankTransferInstruction.objects.create(
                    payment=payment,
                    bank_name=result['bank_name'],
                    account_number=result['account_number'],
                    account_name=result['account_name'],
                    reference_code=payment.paystack_reference,
                    amount_ghs=amount,
                )
                return render(request, 'payments/bank_transfer.html', {
                    'payment': payment,
                    'bank_info': result,
                    'auction': auction,
                })
        else:
            result = paystack.initialize_transaction(payment, callback_url, channel_type)
            if result['success']:
                return redirect(result['authorization_url'])

        messages.error(request, str(result.get('message') or 'Payment initialization failed.'))

    return render(request, 'payments/checkout.html', {
        'auction': auction,
        'amount': amount,
        'paystack_public_key': settings.PAYSTACK_PUBLIC_KEY,
    })


@login_required
def payment_callback(request):
    """Paystack redirects here after card payment"""
    reference = request.GET.get('reference') or request.GET.get('trxref')
    if not reference:
        messages.error(request, 'Invalid payment reference.')
        return redirect('dashboard')

    payment = Payment.objects.filter(
        paystack_reference=reference, user=request.user
    ).first()
    if not payment:
        messages.error(request, 'Payment record not found.')
        return redirect('dashboard_purchases')

    result = paystack.verify_transaction(reference)
    if result['success']:
        if paystack.complete_payment(payment, result['data']):
            messages.success(request, f'Payment of GHS {payment.amount_ghs:,.2f} successful! Funds are held in escrow.')
            if payment.payment_type in [Payment.TYPE_BID_WIN, Payment.TYPE_BUY_NOW]:
                escrow = EscrowAccount.objects.filter(payment=payment).first()
                if escrow:
                    return redirect('escrow_detail', pk=escrow.pk)
            return redirect('dashboard_purchases')
        messages.error(request, 'Payment verification did not match this order.')
    else:
        messages.error(request, result.get('message', 'Payment verification failed.'))

    return redirect('dashboard_purchases')


@login_required
@require_POST
def momo_otp_submit(request):
    """Submit MoMo OTP"""
    otp = request.POST.get('otp')
    reference = request.session.get('pending_momo_reference')
    payment = Payment.objects.filter(
        paystack_reference=reference, user=request.user, status=Payment.STATUS_PENDING
    ).first()
    if not payment or not otp:
        messages.error(request, 'Invalid OTP submission.')
        return redirect('dashboard_purchases')

    result = paystack.submit_momo_otp(reference, otp)
    if result['success']:
        verified = paystack.verify_transaction(reference)
        if verified['success'] and paystack.complete_payment(payment, verified['data']):
            request.session.pop('pending_momo_reference', None)
            messages.success(request, 'MoMo payment successful! Funds held in escrow.')
            return redirect('dashboard_purchases')
        messages.error(request, 'Payment could not be verified.')
    else:
        messages.error(request, str(result.get('message') or 'OTP failed. Try again.'))
    return render(request, 'payments/momo_otp.html', {'payment': payment})


@login_required
def escrow_detail(request, pk):
    """Escrow status page for a transaction"""
    escrow = get_object_or_404(EscrowAccount, pk=pk, buyer=request.user)
    return render(request, 'payments/escrow_detail.html', {'escrow': escrow})


@login_required
@require_POST
def confirm_receipt(request, pk):
    """Buyer confirms item received — triggers escrow release"""
    escrow = get_object_or_404(EscrowAccount, pk=pk, buyer=request.user)
    if escrow.status == EscrowAccount.STATUS_HOLDING:
        if not escrow.buyer_confirmed:
            escrow.buyer_confirmed = True
            escrow.buyer_confirmed_at = timezone.now()
            escrow.save(update_fields=['buyer_confirmed', 'buyer_confirmed_at'])
        result = escrow.release_to_seller()
        if result['status'] == 'success':
            messages.success(request, 'Receipt confirmed and seller payout completed.')
        elif result['status'] == 'pending':
            messages.info(request, 'Receipt confirmed. Paystack is processing the seller payout.')
        else:
            messages.error(request, f"Receipt confirmed, but payout needs attention: {result['message']}")
    return redirect('escrow_detail', pk=pk)


@login_required
@require_POST
def raise_dispute(request, pk):
    """Buyer raises a dispute"""
    escrow = get_object_or_404(EscrowAccount, pk=pk, buyer=request.user)
    if (
        escrow.status == EscrowAccount.STATUS_HOLDING
        and not escrow.buyer_confirmed
        and escrow.payout_status == EscrowAccount.PAYOUT_NOT_STARTED
    ):
        reason = request.POST.get('reason', '')
        if reason.strip():
            escrow.raise_dispute(reason.strip())
            messages.warning(request, 'Dispute raised. Our team will contact you within 24 hours.')
        else:
            messages.error(request, 'Please describe the issue before submitting a dispute.')
    return redirect('escrow_detail', pk=pk)


@csrf_exempt
@require_POST
def paystack_webhook(request):
    """Paystack webhook endpoint — must be registered in Paystack dashboard"""
    signature = request.headers.get('X-Paystack-Signature', '')
    payload_bytes = request.body

    if not paystack.verify_webhook_signature(payload_bytes, signature):
        logger.warning('Invalid Paystack webhook signature')
        return HttpResponse(status=400)

    try:
        payload = json.loads(payload_bytes)
        event = payload.get('event', '')
        data = payload.get('data', {})

        # Log webhook
        PaystackWebhookLog.objects.create(
            event=event,
            reference=data.get('reference', ''),
            payload=payload,
        )

        paystack.handle_webhook_event(event, data)
        return HttpResponse(status=200)

    except Exception as e:
        logger.exception(f'Webhook processing error: {e}')
        return HttpResponse(status=500)
