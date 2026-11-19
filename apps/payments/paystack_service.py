"""
GhanaHammer Paystack Service
Handles: card payments, bank transfers, MTN MoMo, Telecel Cash, AirtelTigo
"""
import hmac
import hashlib
import logging
import re
import requests
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import transaction
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

MOMO_TRANSFER_BANK_CODES = {
    'mtn': 'MTN',
    'mtn_momo': 'MTN',
    'telecel': 'VOD',
    'telecel_cash': 'VOD',
    'airteltigo': 'TGO',
    'airteltigo_money': 'TGO',
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

            if isinstance(data, dict) and data.get('status'):
                d = data.get('data') or {}
                access_code = d.get('access_code')
                authorization_url = d.get('authorization_url')
                if not access_code or not authorization_url:
                    return {'success': False, 'message': 'Payment gateway returned an incomplete checkout response.'}
                payment.paystack_access_code = access_code
                payment.save(update_fields=['paystack_access_code'])
                return {
                    'success': True,
                    'authorization_url': authorization_url,
                    'access_code': access_code,
                    'reference': d.get('reference', payment.paystack_reference),
                }
            message = data.get('message') if isinstance(data, dict) else None
            return {'success': False, 'message': message or 'Initialization failed'}

        except (requests.RequestException, ValueError) as e:
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

            transaction_data = data.get('data') or {} if isinstance(data, dict) else {}
            if isinstance(data, dict) and data.get('status') and transaction_data.get('status') == 'success':
                return {'success': True, 'data': transaction_data}
            return {
                'success': False,
                'message': transaction_data.get('gateway_response', 'Payment not successful'),
            }

        except (requests.RequestException, ValueError) as e:
            logger.exception(f'Paystack verify error: {e}')
            return {'success': False, 'message': 'Could not verify payment.'}

    def complete_payment(self, payment, data):
        """Record a verified Paystack payment once and create its escrow record."""
        from apps.payments.models import Payment, EscrowAccount
        from apps.gh_auctions.models import Auction

        try:
            received_amount = int(data.get('amount'))
        except (TypeError, ValueError):
            received_amount = -1

        if (
            data.get('status') != 'success'
            or data.get('reference') != payment.paystack_reference
            or str(data.get('currency', '')).upper() != 'GHS'
            or received_amount != int(Decimal(payment.amount_ghs) * 100)
        ):
            logger.warning('Paystack payment data did not match order %s', payment.paystack_reference)
            return False

        transitioned = False
        with transaction.atomic():
            locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if locked_payment.status == Payment.STATUS_SUCCESS:
                return True

            auction = None
            if locked_payment.payment_type in [Payment.TYPE_BID_WIN, Payment.TYPE_BUY_NOW]:
                auction_reference = locked_payment.auction
                if not auction_reference:
                    return False
                auction = Auction.objects.select_for_update().filter(
                    pk=auction_reference.pk
                ).first()
                if (
                    not auction
                    or auction.winner != locked_payment.user
                    or auction.status != Auction.STATUS_SOLD
                    or auction.winning_bid_amount != locked_payment.amount_ghs
                ):
                    logger.warning('Winner or amount mismatch for payment %s', locked_payment.paystack_reference)
                    return False

            locked_payment.status = Payment.STATUS_SUCCESS
            locked_payment.paystack_transaction_id = str(data.get('id', ''))
            locked_payment.paystack_response = data
            locked_payment.channel = data.get('channel') or locked_payment.channel
            locked_payment.verified_at = timezone.now()
            locked_payment.save(update_fields=[
                'status', 'paystack_transaction_id', 'paystack_response',
                'channel', 'verified_at', 'updated_at',
            ])
            transitioned = True

            if auction:
                EscrowAccount.objects.get_or_create(
                    payment=locked_payment,
                    defaults={
                        'auction': auction,
                        'buyer': locked_payment.user,
                        'seller': auction.seller,
                        'amount_ghs': locked_payment.amount_ghs,
                    },
                )

        if transitioned:
            from apps.notifications.services import NotificationService
            try:
                NotificationService.notify_payment_success(locked_payment.user, locked_payment)
            except Exception:
                logger.exception('Could not send payment-success notification for %s', locked_payment.paystack_reference)
        return True

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

            response_data = data.get('data') or {} if isinstance(data, dict) else {}
            if isinstance(data, dict) and data.get('status'):
                d = response_data
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

            message = data.get('message') if isinstance(data, dict) else None
            return {'success': False, 'message': message or 'MoMo charge failed'}

        except (requests.RequestException, ValueError) as e:
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
            response_data = data.get('data') or {} if isinstance(data, dict) else {}
            if isinstance(data, dict) and data.get('status') and response_data.get('status') == 'success':
                return {'success': True}
            message = data.get('message') if isinstance(data, dict) else None
            return {'success': False, 'message': message or 'OTP invalid'}
        except (requests.RequestException, ValueError) as e:
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
            account_data = data.get('data') or {} if isinstance(data, dict) else {}
            if isinstance(data, dict) and data.get('status'):
                bank = account_data.get('bank') or {}
                account_number = account_data.get('account_number')
                account_name = account_data.get('account_name')
                if not bank.get('name') or not account_number or not account_name:
                    return {'success': False, 'message': 'Paystack returned incomplete bank-transfer details.'}
                return {
                    'success': True,
                    'bank_name': bank['name'],
                    'account_number': account_number,
                    'account_name': account_name,
                    'reference': payment.paystack_reference,
                }
            message = data.get('message') if isinstance(data, dict) else None
            return {'success': False, 'message': message or 'Could not generate account'}
        except (requests.RequestException, ValueError) as e:
            logger.exception(f'Virtual account error: {e}')
            return {'success': False, 'message': 'Bank transfer gateway unavailable.'}

    def create_transfer_recipient(self, seller):
        """Create a Ghana mobile-money recipient for a seller payout."""
        network = (seller.momo_network or '').strip().lower()
        bank_code = MOMO_TRANSFER_BANK_CODES.get(network)
        phone = re.sub(r'\D', '', seller.momo_number or '')
        if phone.startswith('233') and len(phone) == 12:
            phone = '0' + phone[3:]
        elif len(phone) == 9:
            phone = '0' + phone

        if not bank_code or len(phone) != 10 or not phone.startswith('0'):
            return {
                'success': False,
                'message': 'Seller must save a valid Ghana mobile-money network and number before payout.',
            }

        payload = {
            'type': 'mobile_money',
            'name': seller.get_full_name() or seller.username,
            'account_number': phone,
            'bank_code': bank_code,
            'currency': 'GHS',
        }
        try:
            response = requests.post(
                f'{PAYSTACK_BASE}/transferrecipient',
                json=payload,
                headers=HEADERS(),
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            response_data = result.get('data') or {} if isinstance(result, dict) else {}
            recipient_code = response_data.get('recipient_code')
            if isinstance(result, dict) and result.get('status') and recipient_code:
                return {'success': True, 'recipient_code': recipient_code}
            message = result.get('message') if isinstance(result, dict) else 'Invalid response'
            logger.error('Paystack recipient creation failed: %s', message)
            return {'success': False, 'message': 'Paystack could not create the seller payout recipient.'}
        except (requests.RequestException, ValueError) as exc:
            logger.exception('Paystack recipient creation error: %s', exc)
            return {'success': False, 'message': 'Seller payout recipient could not be created.'}

    def initiate_transfer(self, escrow):
        """Initiate a seller payout using the escrow's stable transfer reference."""
        amount = int(Decimal(escrow.payment.net_to_seller_ghs) * 100)
        if amount <= 0 or not escrow.paystack_recipient_code or not escrow.payout_reference:
            return {'success': False, 'retryable': False, 'message': 'Payout details are incomplete.'}

        payload = {
            'source': 'balance',
            'amount': amount,
            'recipient': escrow.paystack_recipient_code,
            'reference': escrow.payout_reference,
            'reason': f'Seller proceeds for auction {escrow.auction.lot_number}',
        }
        try:
            response = requests.post(
                f'{PAYSTACK_BASE}/transfer',
                json=payload,
                headers=HEADERS(),
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            if isinstance(result, dict) and result.get('status'):
                transfer = result.get('data') or {}
                return {
                    'success': True,
                    'status': transfer.get('status', 'pending'),
                    'transfer_code': transfer.get('transfer_code', ''),
                    'data': transfer,
                }
            message = result.get('message') if isinstance(result, dict) else 'Invalid response'
            logger.error('Paystack transfer initiation failed: %s', message)
            return {'success': False, 'retryable': False, 'message': 'Paystack rejected the seller payout.'}
        except (requests.RequestException, ValueError) as exc:
            logger.exception('Paystack transfer initiation error: %s', exc)
            return {'success': False, 'retryable': True, 'message': 'Payout status is being retried safely.'}

    def release_escrow(self, escrow):
        """Start or resume the payout for an eligible, paid escrow."""
        from apps.payments.models import EscrowAccount, Payment

        with transaction.atomic():
            locked = EscrowAccount.objects.select_for_update().select_related(
                'payment', 'seller', 'auction'
            ).get(pk=escrow.pk)
            if locked.status == EscrowAccount.STATUS_RELEASED:
                return {'success': True, 'status': 'success', 'message': 'Payout already completed.'}
            if locked.status in [EscrowAccount.STATUS_DISPUTED, EscrowAccount.STATUS_REFUNDED]:
                return {'success': False, 'status': 'failed', 'message': 'Disputed or refunded escrow cannot be paid.'}
            if not locked.buyer_confirmed and locked.auto_release_date > timezone.now():
                return {'success': False, 'status': 'pending', 'message': 'Escrow is not eligible for release yet.'}
            if locked.payment.status != Payment.STATUS_SUCCESS:
                return {'success': False, 'status': 'failed', 'message': 'The buyer payment is not confirmed.'}
            if locked.payout_status == EscrowAccount.PAYOUT_PENDING and locked.paystack_transfer_code:
                return {'success': True, 'status': 'pending', 'message': 'Paystack is processing the seller payout.'}

            if not locked.payout_reference:
                locked.payout_reference = uuid.uuid4().hex
            locked.payout_status = EscrowAccount.PAYOUT_PENDING
            locked.payout_error = ''
            locked.save(update_fields=['payout_reference', 'payout_status', 'payout_error'])

        if not locked.paystack_recipient_code:
            recipient = self.create_transfer_recipient(locked.seller)
            if not recipient['success']:
                return self._record_payout_failure(locked.pk, recipient['message'])
            locked.paystack_recipient_code = recipient['recipient_code']
            EscrowAccount.objects.filter(pk=locked.pk).update(
                paystack_recipient_code=locked.paystack_recipient_code
            )

        result = self.initiate_transfer(locked)
        if not result['success']:
            if result.get('retryable'):
                EscrowAccount.objects.filter(pk=locked.pk).update(
                    payout_status=EscrowAccount.PAYOUT_PENDING,
                    payout_error=result['message'],
                )
                return {'success': True, 'status': 'pending', 'message': result['message']}
            return self._record_payout_failure(locked.pk, result['message'])

        EscrowAccount.objects.filter(pk=locked.pk).update(
            paystack_transfer_code=result['transfer_code'],
            payout_status=EscrowAccount.PAYOUT_PENDING,
            payout_error='',
        )
        if result['status'] == 'success':
            self._on_transfer_success(result['data'])
            return {'success': True, 'status': 'success', 'message': 'Seller payout completed.'}
        if result['status'] in ['failed', 'reversed']:
            message = 'Paystack reversed the transfer.' if result['status'] == 'reversed' else 'Paystack transfer failed.'
            self._record_transfer_failure(
                result['data'], message, reversed_transfer=result['status'] == 'reversed'
            )
            return {'success': False, 'status': 'failed', 'message': message}
        return {'success': True, 'status': 'pending', 'message': 'Paystack is processing the seller payout.'}

    def _record_payout_failure(self, escrow_id, message):
        from apps.payments.models import EscrowAccount

        escrow = EscrowAccount.objects.select_related('seller', 'auction').get(pk=escrow_id)
        should_notify = escrow.payout_error != message
        EscrowAccount.objects.filter(pk=escrow_id).update(
            payout_status=EscrowAccount.PAYOUT_FAILED,
            payout_error=message,
        )
        if should_notify:
            try:
                from apps.notifications.services import NotificationService
                NotificationService.create_in_app(
                    escrow.seller,
                    'Seller payout needs attention',
                    'Update your Ghana mobile-money details in Account Settings. The payout will retry automatically when possible.',
                    'warning',
                    escrow.auction,
                )
            except Exception:
                logger.exception('Could not notify seller about payout failure for escrow %s', escrow_id)
        return {'success': False, 'status': 'failed', 'message': message}

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
            'transfer.reversed': self._on_transfer_reversed,
            'refund.failed': self._on_refund_failed,
        }
        handler = handlers.get(event)
        if handler:
            handler(data)
        else:
            logger.info(f'Unhandled Paystack event: {event}')

    def _on_charge_success(self, data):
        from apps.payments.models import Payment

        reference = data.get('reference')
        payment = Payment.objects.filter(paystack_reference=reference).first()
        if not payment:
            logger.warning(f'Payment not found for reference: {reference}')
            return
        if self.complete_payment(payment, data):
            logger.info(f'Payment successful: {reference}')

    def _on_dispute(self, data):
        logger.warning(f'Paystack dispute: {data}')

    def _on_transfer_success(self, data):
        from apps.payments.models import EscrowAccount

        reference = data.get('reference')
        try:
            amount = int(data.get('amount'))
        except (TypeError, ValueError):
            amount = -1

        with transaction.atomic():
            escrow = EscrowAccount.objects.select_for_update().select_related(
                'payment', 'seller', 'buyer', 'auction'
            ).filter(payout_reference=reference).first()
            if not escrow:
                logger.warning('No escrow found for Paystack transfer %s', reference)
                return
            expected_amount = int(Decimal(escrow.payment.net_to_seller_ghs) * 100)
            if (
                str(data.get('currency', '')).upper() != 'GHS'
                or amount != expected_amount
            ):
                logger.error('Paystack transfer details do not match escrow %s', escrow.pk)
                escrow.payout_error = 'Paystack transfer amount or currency did not match escrow.'
                escrow.save(update_fields=['payout_error'])
                return
            if escrow.payout_status == EscrowAccount.PAYOUT_SUCCESS:
                return

            escrow.payout_status = EscrowAccount.PAYOUT_SUCCESS
            escrow.status = EscrowAccount.STATUS_RELEASED
            escrow.released_at = timezone.now()
            escrow.payout_error = ''
            escrow.paystack_transfer_code = data.get('transfer_code') or escrow.paystack_transfer_code
            escrow.save(update_fields=[
                'payout_status', 'status', 'released_at', 'payout_error',
                'paystack_transfer_code',
            ])

        from apps.notifications.services import NotificationService
        for user, title, message in [
            (
                escrow.seller,
                'Payout sent',
                f'GHS {escrow.payment.net_to_seller_ghs:,.2f} was sent for lot {escrow.auction.lot_number}.',
            ),
            (
                escrow.buyer,
                'Seller payout completed',
                f'The seller was paid for lot {escrow.auction.lot_number}.',
            ),
        ]:
            try:
                NotificationService.create_in_app(user, title, message, 'success', escrow.auction)
            except Exception:
                logger.exception('Could not send payout notification for escrow %s', escrow.pk)

    def _on_transfer_failed(self, data):
        self._record_transfer_failure(data, 'Paystack transfer failed.')

    def _on_transfer_reversed(self, data):
        self._record_transfer_failure(data, 'Paystack reversed the transfer.', reversed_transfer=True)

    def _record_transfer_failure(self, data, message, reversed_transfer=False):
        from apps.payments.models import EscrowAccount

        reference = data.get('reference')
        with transaction.atomic():
            escrow = EscrowAccount.objects.select_for_update().filter(
                payout_reference=reference
            ).first()
            if not escrow or (
                escrow.payout_status == EscrowAccount.PAYOUT_SUCCESS
                and not reversed_transfer
            ):
                return
            escrow.payout_status = EscrowAccount.PAYOUT_FAILED
            escrow.payout_error = message
            fields = ['payout_status', 'payout_error']
            if reversed_transfer:
                escrow.status = EscrowAccount.STATUS_HOLDING
                escrow.released_at = None
                escrow.payout_reference = None
                escrow.paystack_transfer_code = ''
                fields.extend(['status', 'released_at', 'payout_reference', 'paystack_transfer_code'])
            escrow.save(update_fields=fields)
        logger.error('%s Escrow %s, transfer %s', message, escrow.pk, reference)

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
