"""apps/payments/subscription_views.py — Subscription plan checkout"""
import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.contrib import messages
from django.urls import reverse
from apps.payments.models import Payment, BankTransferInstruction
from apps.payments.paystack_service import PaystackService

logger = logging.getLogger(__name__)
_paystack = PaystackService()


@login_required
def subscription_checkout(request):
    """Handle subscription plan and bid credit payment initiation"""
    if request.method != 'POST':
        return redirect('dashboard_subscription')

    plan = request.POST.get('plan', '')
    amount_str = request.POST.get('amount', '0')
    pkg_id = request.POST.get('pkg_id', '')
    channel_type = request.POST.get('channel_type', 'card')
    momo_number = request.POST.get('momo_number', '')
    momo_network = request.POST.get('momo_network', '')

    try:
        amount = float(amount_str)
    except (ValueError, TypeError):
        messages.error(request, 'Invalid amount.')
        return redirect('dashboard_subscription')

    if pkg_id:
        from apps.bidding.models import BidCreditPackage
        try:
            pkg = BidCreditPackage.objects.get(id=pkg_id, is_active=True)
            amount = float(pkg.price_ghs)
            payment_type = Payment.TYPE_CREDITS
        except BidCreditPackage.DoesNotExist:
            messages.error(request, 'Credit package not found.')
            return redirect('dashboard_subscription')
    else:
        payment_type = Payment.TYPE_SUBSCRIPTION

    payment = Payment.objects.create(
        user=request.user,
        payment_type=payment_type,
        amount_ghs=amount,
        channel=channel_type,
        momo_number=momo_number,
        momo_network=momo_network,
        paystack_response={'plan': plan, 'pkg_id': pkg_id},
    )

    callback_url = request.build_absolute_uri(reverse('payment_callback'))

    if channel_type == 'mobile_money' and momo_number:
        result = _paystack.charge_mobile_money(payment)
        if result['success'] and result.get('requires_action'):
            request.session['pending_momo_reference'] = payment.paystack_reference
            messages.info(request, result.get('message', 'Approve payment on your phone.'))
            return redirect('dashboard_subscription')
        elif not result['success']:
            messages.error(request, result.get('message', 'Mobile money charge failed.'))
            return redirect('dashboard_subscription')

    elif channel_type == 'bank_transfer':
        result = _paystack.create_dedicated_virtual_account(payment)
        if result['success']:
            BankTransferInstruction.objects.create(
                payment=payment,
                bank_name=result['bank_name'],
                account_number=result['account_number'],
                account_name=result['account_name'],
                reference_code=payment.paystack_reference,
                amount_ghs=amount,
            )
            messages.info(
                request,
                f'Transfer GHS {amount:,.2f} to {result["bank_name"]}, '
                f'account {result["account_number"]} '
                f'(ref: {payment.paystack_reference}). '
                f'Your plan activates once payment clears.'
            )
            return redirect('dashboard_subscription')
        else:
            messages.error(request, result.get('message', 'Could not create bank account.'))
            return redirect('dashboard_subscription')

    else:
        result = _paystack.initialize_transaction(payment, callback_url, channel_type)
        if result['success']:
            return redirect(result['authorization_url'])
        messages.error(request, result.get('message', 'Payment initialization failed.'))

    return redirect('dashboard_subscription')
