"""GhanaHammer Payment Views"""
import json
import logging
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.conf import settings
from django.urls import reverse

from apps.payments.models import Payment, EscrowAccount, BankTransferInstruction, PaystackWebhookLog
from apps.payments.paystack_service import PaystackService
from apps.gh_auctions.models import Auction

logger = logging.getLogger(__name__)
paystack = PaystackService()


@login_required
def checkout(request, auction_id):
    """Checkout page for auction win payment"""
    auction = get_object_or_404(Auction, id=auction_id)

    # Ensure user is the winner
    if auction.winner != request.user:
        messages.error(request, 'You are not the winner of this auction.')
        return redirect('auction_detail', slug=auction.slug)

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
                messages.info(request, result['message'])
                return render(request, 'payments/momo_otp.html', {'payment': payment})
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

        messages.error(request, result.get('message', 'Payment initialization failed.'))

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

    result = paystack.verify_transaction(reference)
    if result['success']:
        try:
            payment = Payment.objects.get(paystack_reference=reference)
            payment.status = Payment.STATUS_SUCCESS
            payment.paystack_transaction_id = str(result['data'].get('id', ''))
            payment.paystack_response = result['data']
            payment.verified_at = timezone.now()
            payment.save()

            # Create escrow
            if payment.auction:
                EscrowAccount.objects.get_or_create(
                    payment=payment,
                    defaults={
                        'auction': payment.auction,
                        'buyer': payment.user,
                        'seller': payment.auction.seller,
                        'amount_ghs': payment.amount_ghs,
                    }
                )

            messages.success(request, f'Payment of GHS {payment.amount_ghs:,.2f} successful! Funds are held in escrow.')
            return redirect('escrow_detail', pk=payment.escrow.pk)

        except Payment.DoesNotExist:
            messages.error(request, 'Payment record not found.')
    else:
        messages.error(request, result.get('message', 'Payment verification failed.'))

    return redirect('dashboard')


@login_required
def momo_otp_submit(request):
    """Submit MoMo OTP"""
    if request.method == 'POST':
        otp = request.POST.get('otp')
        reference = request.session.get('pending_momo_reference')
        if not reference or not otp:
            messages.error(request, 'Invalid OTP submission.')
            return redirect('dashboard')

        result = paystack.submit_momo_otp(reference, otp)
        if result['success']:
            messages.success(request, 'MoMo payment successful! Funds held in escrow.')
            del request.session['pending_momo_reference']
            return redirect('dashboard_purchases')
        else:
            messages.error(request, result.get('message', 'OTP failed. Try again.'))
            return render(request, 'payments/momo_otp.html', {'reference': reference})

    return redirect('dashboard')


@login_required
def escrow_detail(request, pk):
    """Escrow status page for a transaction"""
    escrow = get_object_or_404(EscrowAccount, pk=pk, buyer=request.user)
    return render(request, 'payments/escrow_detail.html', {'escrow': escrow})


@login_required
def confirm_receipt(request, pk):
    """Buyer confirms item received — triggers escrow release"""
    escrow = get_object_or_404(EscrowAccount, pk=pk, buyer=request.user)
    if request.method == 'POST' and escrow.status == EscrowAccount.STATUS_HOLDING:
        escrow.buyer_confirmed = True
        escrow.buyer_confirmed_at = timezone.now()
        escrow.release_to_seller()
        messages.success(request, 'Receipt confirmed. Funds released to seller.')
    return redirect('escrow_detail', pk=pk)


@login_required
def raise_dispute(request, pk):
    """Buyer raises a dispute"""
    escrow = get_object_or_404(EscrowAccount, pk=pk, buyer=request.user)
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        escrow.raise_dispute(reason)
        messages.warning(request, 'Dispute raised. Our team will contact you within 24 hours.')
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
