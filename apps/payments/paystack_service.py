"""
GhanaHammer Paystack Service
Handles: card payments, bank transfers, MTN MoMo, Telecel Cash, AirtelTigo
"""
import hmac
import hashlib
import logging
import requests
from decimal import Decimal
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

PAYSTACK_BASE = 'https://api.paystack.co'
HEADERS = lambda: {
    'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
    'Content-Type': 'application/json',
}

# Paystack mobile money provider codes
MOMO_PROVIDERS = {
    'mtn_momo': 'mtn',
    'telecel_cash': 'vod',       # Vodafone/Telecel
    'airteltigo_money': 'tgo',
}


class PaystackService:

    # ─────────────────────────────────────────────────────────────
    # INITIALIZE TRANSACTION
    # ─────────────────────────────────────────────────────────────

    def initialize_transaction(self, payment, callback_url, channel_type='card'):
        """
        Initialize any Paystack transaction.
        channel_type: 'card' | 'bank_transfer' | 'mobile_money'
        Returns: {authorization_url, access_code, reference}
        """
        amount_kobo = int(payment.amount_ghs * 100)  # Paystack uses smallest currency unit

        payload = {
            'email': payment.user.email,
            'amount': amount_kobo,
            'reference': payment.paystack_reference,
            'callback_url': callback_url,
            'currency': 'GHS',
            'metadata': {
                'payment_id': str(payment.id),
                'payment_type': payment.payment_type,
                'user_id': str(payment.user.id),
                'custom_fields': [
                    {'display_name': 'Platform', 'variable_name': 'platform', 'value': 'GhanaHammer'},
                    {'display_name': 'Payment Type', 'variable_name': 'type', 'value': payment.get_payment_type_display()},
                ]
            },
        }

        if channel_type == 'card':
            payload['channels'] = ['card']
        elif channel_type == 'bank_transfer':
            payload['channels'] = ['bank_transfer']
        elif channel_type == 'mobile_money':
            payload['channels'] = ['mobile_money']
            if payment.momo_number and payment.momo_network:
                provider = MOMO_PROVIDERS.get(payment.momo_network, 'mtn')
                payload['mobile_money'] = {
                    'phone': payment.momo_number,
                    'provider': provider,
                }

        try:
            resp = requests.post(
                f'{PAYSTACK_BASE}/transaction/initialize',
                json=payload,
                headers=HEADERS(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get('status'):
                d = data['data']
                payment.paystack_access_code = d['access_code']
                payment.save(update_fields=['paystack_access_code'])
                return {
                    'success': True,
                    'authorization_url': d['authorization_url'],
                    'access_code': d['access_code'],
                    'reference': d['reference'],
                }
            return {'success': False, 'message': data.get('message', 'Initialization failed')}

        except requests.RequestException as e:
            logger.exception(f'Paystack init error: {e}')
            return {'success': False, 'message': 'Payment gateway unavailable. Please try again.'}

    # ─────────────────────────────────────────────────────────────
    # VERIFY TRANSACTION
    # ─────────────────────────────────────────────────────────────

    def verify_transaction(self, reference):
        """Verify a transaction by reference. Called from callback and webhook."""
        try:
            resp = requests.get(
                f'{PAYSTACK_BASE}/transaction/verify/{reference}',
                headers=HEADERS(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get('status') and data['data']['status'] == 'success':
                return {'success': True, 'data': data['data']}
            return {'success': False, 'message': data['data'].get('gateway_response', 'Payment not successful')}

        except requests.RequestException as e:
            logger.exception(f'Paystack verify error: {e}')
            return {'success': False, 'message': 'Could not verify payment.'}

    # ─────────────────────────────────────────────────────────────
    # MOBILE MONEY – CHARGE
    # ─────────────────────────────────────────────────────────────

    def charge_mobile_money(self, payment):
        """
        Directly charge a mobile money number (USSD push).
        Used for MTN MoMo, Telecel Cash, AirtelTigo.
        """
        provider = MOMO_PROVIDERS.get(payment.momo_network, 'mtn')
        amount_kobo = int(payment.amount_ghs * 100)

        payload = {
            'email': payment.user.email,
            'amount': amount_kobo,
            'currency': 'GHS',
            'mobile_money': {
                'phone': payment.momo_number,
                'provider': provider,
            },
            'reference': payment.paystack_reference,
            'metadata': {
                'payment_id': str(payment.id),
                'payment_type': payment.payment_type,
            },
        }

        try:
            resp = requests.post(
                f'{PAYSTACK_BASE}/charge',
                json=payload,
                headers=HEADERS(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get('status'):
                d = data['data']
                status = d.get('status')
                if status in ('send_otp', 'pending', 'pay_offline'):
                    return {
                        'success': True,
                        'requires_action': True,
                        'status': status,
                        'message': d.get('display_text', 'Approve the payment on your phone.'),
                        'reference': payment.paystack_reference,
                    }
                elif status == 'success':
                    return {'success': True, 'requires_action': False}

            return {'success': False, 'message': data.get('message', 'MoMo charge failed')}

        except requests.RequestException as e:
            logger.exception(f'MoMo charge error: {e}')
            return {'success': False, 'message': 'Mobile money gateway unavailable.'}

    def submit_momo_otp(self, reference, otp):
        """Submit OTP for mobile money charge"""
        try:
            resp = requests.post(
                f'{PAYSTACK_BASE}/charge/submit_otp',
                json={'otp': otp, 'reference': reference},
                headers=HEADERS(),
                timeout=30,
            )
            data = resp.json()
            if data.get('status') and data['data'].get('status') == 'success':
                return {'success': True}
            return {'success': False, 'message': data.get('message', 'OTP invalid')}
        except requests.RequestException as e:
            logger.exception(f'MoMo OTP error: {e}')
            return {'success': False, 'message': 'OTP submission failed.'}

    # ─────────────────────────────────────────────────────────────
    # BANK TRANSFER – CREATE VIRTUAL ACCOUNT
    # ─────────────────────────────────────────────────────────────

    def create_dedicated_virtual_account(self, payment):
        """
        Create a dedicated virtual bank account for a payment.
        Buyer sends exact amount to this account number.
        """
        # First, ensure customer exists in Paystack
        customer_code = self._get_or_create_customer(payment.user)
        if not customer_code:
            return {'success': False, 'message': 'Could not create Paystack customer.'}

        payload = {
            'customer': customer_code,
            'preferred_bank': 'wema-bank',
            'amount': int(payment.amount_ghs * 100),
        }

        try:
            resp = requests.post(
                f'{PAYSTACK_BASE}/dedicated_account',
                json=payload,
                headers=HEADERS(),
                timeout=30,
            )
            data = resp.json()
            if data.get('status'):
                d = data['data']
                return {
                    'success': True,
                    'bank_name': d['bank']['name'],
                    'account_number': d['account_number'],
                    'account_name': d['account_name'],
                    'reference': payment.paystack_reference,
                }
            return {'success': False, 'message': data.get('message', 'Could not generate account')}
        except requests.RequestException as e:
            logger.exception(f'Virtual account error: {e}')
            return {'success': False, 'message': 'Bank transfer gateway unavailable.'}

    # ─────────────────────────────────────────────────────────────
    # REFUND
    # ─────────────────────────────────────────────────────────────

    def refund_transaction(self, transaction_id, amount_ghs=None):
        """Issue a full or partial refund"""
        payload = {'transaction': transaction_id}
        if amount_ghs:
            payload['amount'] = int(amount_ghs * 100)

        try:
            resp = requests.post(
                f'{PAYSTACK_BASE}/refund',
                json=payload,
                headers=HEADERS(),
                timeout=30,
            )
            data = resp.json()
            return {'success': data.get('status', False), 'data': data.get('data', {})}
        except requests.RequestException as e:
            logger.exception(f'Refund error: {e}')
            return {'success': False, 'message': 'Refund failed.'}

    # ─────────────────────────────────────────────────────────────
    # WEBHOOK VERIFICATION
    # ─────────────────────────────────────────────────────────────

    def verify_webhook_signature(self, payload_bytes, signature_header):
        """Verify Paystack webhook HMAC-SHA512 signature"""
        secret = settings.PAYSTACK_SECRET_KEY.encode('utf-8')
        computed = hmac.new(secret, payload_bytes, hashlib.sha512).hexdigest()
        return hmac.compare_digest(computed, signature_header)

    # ─────────────────────────────────────────────────────────────
    # WEBHOOK EVENT HANDLER
    # ─────────────────────────────────────────────────────────────

    def handle_webhook_event(self, event, data):
        """
        Route Paystack webhook events to the appropriate handler.
        Called from the webhook view after signature verification.
        """
        handlers = {
            'charge.success': self._on_charge_success,
            'charge.dispute.create': self._on_dispute,
            'transfer.success': self._on_transfer_success,
            'transfer.failed': self._on_transfer_failed,
            'refund.failed': self._on_refund_failed,
        }
        handler = handlers.get(event)
        if handler:
            handler(data)
        else:
            logger.info(f'Unhandled Paystack event: {event}')

    def _on_charge_success(self, data):
        from apps.payments.models import Payment, EscrowAccount
        from apps.notifications.services import NotificationService

        reference = data.get('reference')
        try:
            payment = Payment.objects.get(paystack_reference=reference)
        except Payment.DoesNotExist:
            logger.warning(f'Payment not found for reference: {reference}')
            return

        payment.status = Payment.STATUS_SUCCESS
        payment.paystack_transaction_id = str(data.get('id', ''))
        payment.paystack_response = data
        payment.channel = data.get('channel', '')
        payment.verified_at = timezone.now()
        payment.save()

        # Create escrow for auction win or buy-now payments
        if payment.payment_type in [Payment.TYPE_BID_WIN, Payment.TYPE_BUY_NOW]:
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
                # Mark auction as sold
                auction = payment.auction
                auction.status = 'sold'
                auction.save(update_fields=['status'])

        NotificationService.notify_payment_success(payment.user, payment)
        logger.info(f'Payment successful: {reference}')

    def _on_dispute(self, data):
        logger.warning(f'Paystack dispute: {data}')

    def _on_transfer_success(self, data):
        logger.info(f'Transfer successful: {data}')

    def _on_transfer_failed(self, data):
        logger.error(f'Transfer failed: {data}')

    def _on_refund_failed(self, data):
        logger.error(f'Refund failed: {data}')

    # ─────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────

    def _get_or_create_customer(self, user):
        """Get or create Paystack customer, return customer_code"""
        try:
            resp = requests.post(
                f'{PAYSTACK_BASE}/customer',
                json={
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'phone': user.phone,
                },
                headers=HEADERS(),
                timeout=30,
            )
            data = resp.json()
            if data.get('status'):
                return data['data']['customer_code']
        except Exception as e:
            logger.exception(f'Customer creation error: {e}')
        return None
