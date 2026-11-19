import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.gh_accounts.models import User
from apps.gh_auctions.models import Auction, Category
from apps.payments.models import EscrowAccount, Payment
from apps.payments.paystack_service import PaystackService
from apps.payments.views import release_mature_escrow_cron


class PaystackPayoutServiceTests(SimpleTestCase):
    @patch('apps.payments.paystack_service.requests.post')
    def test_creates_ghana_momo_recipient(self, post):
        response = Mock()
        response.json.return_value = {
            'status': True,
            'data': {'recipient_code': 'RCP_test'},
        }
        post.return_value = response
        seller = SimpleNamespace(
            momo_network='mtn',
            momo_number='+233 24 123 4567',
            username='seller',
            get_full_name=lambda: 'Seller Name',
        )

        result = PaystackService().create_transfer_recipient(seller)

        self.assertEqual(result, {'success': True, 'recipient_code': 'RCP_test'})
        self.assertEqual(post.call_args.kwargs['json'], {
            'type': 'mobile_money',
            'name': 'Seller Name',
            'account_number': '0241234567',
            'bank_code': 'MTN',
            'currency': 'GHS',
        })

    @patch('apps.payments.paystack_service.requests.post')
    def test_transfer_sends_net_seller_amount_with_stable_reference(self, post):
        response = Mock()
        response.json.return_value = {
            'status': True,
            'data': {'status': 'pending', 'transfer_code': 'TRF_test'},
        }
        post.return_value = response
        escrow = SimpleNamespace(
            payment=SimpleNamespace(net_to_seller_ghs=Decimal('95.50')),
            paystack_recipient_code='RCP_test',
            payout_reference='a' * 32,
            auction=SimpleNamespace(lot_number='GH-1001'),
        )

        result = PaystackService().initiate_transfer(escrow)

        self.assertEqual(result['status'], 'pending')
        self.assertEqual(post.call_args.kwargs['json'], {
            'source': 'balance',
            'amount': 9550,
            'recipient': 'RCP_test',
            'reference': 'a' * 32,
            'reason': 'Seller proceeds for auction GH-1001',
        })

    @patch('apps.payments.paystack_service.requests.post', side_effect=requests.Timeout)
    def test_transfer_timeout_is_marked_retryable(self, post):
        escrow = SimpleNamespace(
            payment=SimpleNamespace(net_to_seller_ghs=Decimal('95.50')),
            paystack_recipient_code='RCP_test',
            payout_reference='b' * 32,
            auction=SimpleNamespace(lot_number='GH-1001'),
        )

        result = PaystackService().initiate_transfer(escrow)

        self.assertFalse(result['success'])
        self.assertTrue(result['retryable'])


class VercelPayoutCronTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(CRON_SECRET='test-cron-secret')
    def test_rejects_missing_or_invalid_bearer_secret(self):
        response = release_mature_escrow_cron(self.factory.get('/api/cron/release-mature-escrow/'))
        self.assertEqual(response.status_code, 401)

    @override_settings(CRON_SECRET='')
    def test_fails_closed_when_cron_secret_is_not_configured(self):
        response = release_mature_escrow_cron(self.factory.get('/api/cron/release-mature-escrow/'))
        self.assertEqual(response.status_code, 503)

    @override_settings(CRON_SECRET='test-cron-secret', VERCEL_CRON_ENABLED=False)
    @patch('apps.payments.tasks.release_mature_escrow')
    def test_disabled_cron_does_not_run_payout_task(self, release_task):
        response = release_mature_escrow_cron(self.factory.get('/api/cron/release-mature-escrow/'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {'disabled': True})
        release_task.assert_not_called()

    @override_settings(CRON_SECRET='test-cron-secret')
    @patch('apps.payments.tasks.release_mature_escrow', return_value='Completed 0 payouts; 0 payouts pending')
    def test_runs_release_task_with_valid_bearer_secret(self, release_task):
        request = self.factory.get(
            '/api/cron/release-mature-escrow/',
            HTTP_AUTHORIZATION='Bearer test-cron-secret',
        )

        response = release_mature_escrow_cron(request)

        self.assertEqual(response.status_code, 200)
        release_task.assert_called_once_with()


class EscrowPayoutIntegrationTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.buyer = User.objects.create_user(
            username='buyer', email='buyer@example.com', password='test-password'
        )
        self.seller = User.objects.create_user(
            username='seller',
            email='seller@example.com',
            password='test-password',
            momo_network='mtn',
            momo_number='0241234567',
        )
        category = Category.objects.create(name='Vehicles', slug='vehicles')
        auction = Auction.objects.create(
            title='Test vehicle',
            description='Test auction item',
            seller=self.seller,
            category=category,
            starting_price=Decimal('100.00'),
            current_price=Decimal('100.00'),
            start_time=now,
            end_time=now,
            status=Auction.STATUS_SOLD,
            winner=self.buyer,
            winning_bid_amount=Decimal('100.00'),
        )
        payment = Payment.objects.create(
            user=self.buyer,
            auction=auction,
            payment_type=Payment.TYPE_BID_WIN,
            amount_ghs=Decimal('100.00'),
            status=Payment.STATUS_SUCCESS,
        )
        self.escrow = EscrowAccount.objects.create(
            payment=payment,
            auction=auction,
            buyer=self.buyer,
            seller=self.seller,
            amount_ghs=Decimal('100.00'),
            buyer_confirmed=True,
            auto_release_date=now,
        )

    @patch('apps.notifications.services.NotificationService.create_in_app')
    @patch('apps.payments.paystack_service.requests.post')
    def test_payout_completes_only_after_success_webhook(self, post, notify):
        def paystack_response(url, **kwargs):
            response = Mock()
            if url.endswith('/transferrecipient'):
                response.json.return_value = {
                    'status': True,
                    'data': {'recipient_code': 'RCP_test'},
                }
            else:
                response.json.return_value = {
                    'status': True,
                    'data': {
                        'status': 'pending',
                        'transfer_code': 'TRF_test',
                        'reference': kwargs['json']['reference'],
                        'amount': 9500,
                        'currency': 'GHS',
                    },
                }
            return response

        post.side_effect = paystack_response
        service = PaystackService()

        result = service.release_escrow(self.escrow)
        self.assertEqual(result['status'], 'pending')
        self.escrow.refresh_from_db()
        self.assertEqual(self.escrow.status, EscrowAccount.STATUS_HOLDING)
        self.assertEqual(self.escrow.payout_status, EscrowAccount.PAYOUT_PENDING)
        self.assertEqual(self.escrow.payment.net_to_seller_ghs, Decimal('95.00'))

        service.handle_webhook_event('transfer.success', {
            'reference': self.escrow.payout_reference,
            'transfer_code': 'TRF_test',
            'amount': 9500,
            'currency': 'GHS',
        })

        self.escrow.refresh_from_db()
        self.assertEqual(self.escrow.status, EscrowAccount.STATUS_RELEASED)
        self.assertEqual(self.escrow.payout_status, EscrowAccount.PAYOUT_SUCCESS)
        self.assertIsNotNone(self.escrow.released_at)
        self.assertEqual(notify.call_count, 2)