from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.gh_accounts.models import User
from apps.gh_auctions.models import Auction, Category
from apps.gh_auctions.tasks import activate_scheduled_auctions, close_expired_auctions
from apps.bidding.models import Bid
from apps.payments.models import Payment
from apps.bidding.consumers import AuctionBiddingConsumer


class SubscriptionAndCreditRemovalTests(TestCase):
    """Verify that subscription plans, subscription models, and bid credits have been removed."""

    def test_user_model_has_no_subscription_or_credit_fields(self):
        user_field_names = [f.name for f in User._meta.get_fields()]
        self.assertNotIn('plan', user_field_names)
        self.assertNotIn('plan_expiry', user_field_names)
        self.assertNotIn('bid_credits', user_field_names)

    def test_user_properties_always_grant_access(self):
        user = User(username='testmember', email='test@example.com')
        self.assertTrue(user.can_early_access)
        self.assertTrue(user.is_plan_active)

    def test_subscription_models_removed(self):
        import apps.gh_accounts.models as account_models
        import apps.bidding.models as bidding_models

        self.assertFalse(hasattr(account_models, 'SubscriptionPayment'))
        self.assertFalse(hasattr(bidding_models, 'BidCreditPackage'))
        self.assertFalse(hasattr(bidding_models, 'BidCreditTransaction'))

    def test_payment_types_do_not_contain_subscription_or_credits(self):
        payment_types = [choice[0] for choice in Payment.TYPE_CHOICES]
        self.assertNotIn('subscription', payment_types)
        self.assertNotIn('bid_credits', payment_types)


class ExclusiveAuctionPrivilegesTests(TestCase):
    """Verify that preview and VIP-only auctions are accessible to all signed-in users,
    while unauthenticated users are filtered out or redirected to login.
    """

    def setUp(self):
        self.client = Client()
        self.seller = User.objects.create_user(
            username='seller', email='seller@example.com', password='password123', is_staff=True
        )
        self.member = User.objects.create_user(
            username='member', email='member@example.com', password='password123', is_staff=False
        )
        self.category = Category.objects.create(name='Heavy Machinery', slug='heavy-machinery')

        now = timezone.now()
        # 1. Regular active auction
        self.regular_auction = Auction.objects.create(
            lot_number='GH-1001',
            title='Standard Generator',
            slug='standard-generator',
            description='Standard generator description',
            seller=self.seller,
            category=self.category,
            starting_price=Decimal('500.00'),
            current_price=Decimal('500.00'),
            start_time=now - timedelta(hours=2),
            end_time=now + timedelta(days=2),
            status=Auction.STATUS_ACTIVE,
            is_vip_only=False,
        )

        # 2. Preview auction (early access)
        self.preview_auction = Auction.objects.create(
            lot_number='GH-1002',
            title='Preview Excavator',
            slug='preview-excavator',
            description='Preview excavator description',
            seller=self.seller,
            category=self.category,
            starting_price=Decimal('20000.00'),
            current_price=Decimal('20000.00'),
            preview_start=now - timedelta(hours=1),
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=3),
            status=Auction.STATUS_PREVIEW,
            is_vip_only=False,
        )

        # 3. VIP-only auction
        self.vip_auction = Auction.objects.create(
            lot_number='GH-1003',
            title='VIP Bulldozer',
            slug='vip-bulldozer',
            description='VIP bulldozer description',
            seller=self.seller,
            category=self.category,
            starting_price=Decimal('50000.00'),
            current_price=Decimal('50000.00'),
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(days=2),
            status=Auction.STATUS_ACTIVE,
            is_vip_only=True,
        )

    def test_unauthenticated_user_cannot_see_preview_or_vip_in_list(self):
        response = self.client.get(reverse('auction_list'))
        self.assertEqual(response.status_code, 200)
        auctions = list(response.context['auctions'])
        auction_ids = [a.id for a in auctions]
        self.assertIn(self.regular_auction.id, auction_ids)
        self.assertNotIn(self.preview_auction.id, auction_ids)
        self.assertNotIn(self.vip_auction.id, auction_ids)

    def test_signed_in_member_can_see_preview_and_vip_in_list(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('auction_list'))
        self.assertEqual(response.status_code, 200)
        auctions = list(response.context['auctions'])
        auction_ids = [a.id for a in auctions]
        self.assertIn(self.regular_auction.id, auction_ids)
        self.assertIn(self.preview_auction.id, auction_ids)
        self.assertIn(self.vip_auction.id, auction_ids)

    def test_unauthenticated_user_redirected_on_preview_detail(self):
        response = self.client.get(reverse('auction_detail', kwargs={'slug': self.preview_auction.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('account_login'), response.url)

    def test_unauthenticated_user_redirected_on_vip_detail(self):
        response = self.client.get(reverse('auction_detail', kwargs={'slug': self.vip_auction.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('account_login'), response.url)

    def test_signed_in_member_can_access_preview_detail(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('auction_detail', kwargs={'slug': self.preview_auction.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['auction'].id, self.preview_auction.id)

    def test_signed_in_member_can_access_vip_detail(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('auction_detail', kwargs={'slug': self.vip_auction.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['auction'].id, self.vip_auction.id)


class AdminListingCreationRestrictionsTests(TestCase):
    """Verify that listing creation/editing is restricted strictly to administrators/staff."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='adminuser', email='admin@example.com', password='password123', is_staff=True
        )
        self.member = User.objects.create_user(
            username='regularmember', email='member2@example.com', password='password123', is_staff=False
        )

    def test_unauthenticated_user_cannot_access_create(self):
        response = self.client.get(reverse('auction_create'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('auction_list'))

    def test_regular_signed_in_member_cannot_access_create(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('auction_create'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('auction_list'))

    def test_admin_can_access_create(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('auction_create'))
        self.assertEqual(response.status_code, 200)

    def test_regular_member_cannot_access_bulk_import(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('bulk_import'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('auction_list'))

    def test_admin_can_access_bulk_import(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('bulk_import'))
        self.assertEqual(response.status_code, 200)


class AuctionTasksTests(TestCase):
    """Verify auction background tasks logic."""

    def setUp(self):
        self.seller = User.objects.create_user(
            username='seller3', email='seller3@example.com', password='password123', is_staff=True
        )
        self.buyer = User.objects.create_user(
            username='buyer3', email='buyer3@example.com', password='password123', phone='+233240000000'
        )
        self.category = Category.objects.create(name='Machinery', slug='machinery')

    @patch('apps.gh_auctions.tasks.check_saved_searches_for_auction.delay')
    def test_activate_scheduled_and_preview_auctions(self, mock_saved_searches):
        now = timezone.now()
        # Scheduled auction whose start_time has arrived
        sched_due = Auction.objects.create(
            lot_number='GH-2001',
            title='Due Scheduled',
            slug='due-scheduled',
            description='Desc',
            seller=self.seller,
            category=self.category,
            starting_price=Decimal('100.00'),
            current_price=Decimal('100.00'),
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(days=1),
            status=Auction.STATUS_SCHEDULED,
        )

        # Preview auction whose start_time has arrived (transition from preview to active)
        prev_due = Auction.objects.create(
            lot_number='GH-2002',
            title='Due Preview',
            slug='due-preview',
            description='Desc',
            seller=self.seller,
            category=self.category,
            starting_price=Decimal('100.00'),
            current_price=Decimal('100.00'),
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(days=1),
            status=Auction.STATUS_PREVIEW,
        )

        # Future scheduled auction that should not activate yet
        future_sched = Auction.objects.create(
            lot_number='GH-2003',
            title='Future Sched',
            slug='future-sched',
            description='Desc',
            seller=self.seller,
            category=self.category,
            starting_price=Decimal('100.00'),
            current_price=Decimal('100.00'),
            start_time=now + timedelta(hours=5),
            end_time=now + timedelta(days=2),
            status=Auction.STATUS_SCHEDULED,
        )

        activate_scheduled_auctions()

        sched_due.refresh_from_db()
        prev_due.refresh_from_db()
        future_sched.refresh_from_db()

        self.assertEqual(sched_due.status, Auction.STATUS_ACTIVE)
        self.assertEqual(prev_due.status, Auction.STATUS_ACTIVE)
        self.assertEqual(future_sched.status, Auction.STATUS_SCHEDULED)

    @patch('apps.notifications.services.NotificationService.create_in_app')
    @patch('apps.notifications.services.NotificationService.notify_auction_won')
    @patch('apps.notifications.services.NotificationService.notify_seller_sale')
    def test_close_expired_auctions_records_winner_details(self, mock_notify_seller, mock_notify_buyer, mock_create_in_app):
        now = timezone.now()
        auction = Auction.objects.create(
            lot_number='GH-3001',
            title='Expired Auction',
            slug='expired-auction',
            description='Desc',
            seller=self.seller,
            category=self.category,
            starting_price=Decimal('100.00'),
            current_price=Decimal('250.00'),
            start_time=now - timedelta(days=2),
            end_time=now - timedelta(minutes=10),
            status=Auction.STATUS_ACTIVE,
        )

        Bid.objects.create(
            auction=auction,
            bidder=self.buyer,
            bidder_name='Buyer Three',
            bidder_email='buyer3@example.com',
            bidder_phone='0241234567',
            pickup_notes='Pickup from warehouse A',
            amount=Decimal('250.00'),
            status=Bid.STATUS_WINNING,
        )

        close_expired_auctions()

        auction.refresh_from_db()
        self.assertEqual(auction.status, Auction.STATUS_SOLD)
        self.assertEqual(auction.winner, self.buyer)
        self.assertEqual(auction.winning_bid_amount, Decimal('250.00'))
        self.assertEqual(auction.winner_email, 'buyer3@example.com')
        self.assertEqual(auction.winner_phone, '0241234567')
        self.assertEqual(auction.winner_pickup_notes, 'Pickup from warehouse A')


class BiddingConsumerSignatureTests(TestCase):
    """Verify consumer accepts bids without requiring credit parameters."""

    def test_place_bid_signature(self):
        consumer = AuctionBiddingConsumer()
        import inspect
        sig = inspect.signature(consumer.place_bid)
        params = list(sig.parameters.keys())
        self.assertIn('amount', params)
        self.assertIn('bidder_name', params)
        self.assertIn('bidder_email', params)
        self.assertIn('bidder_phone', params)
        self.assertIn('pickup_notes', params)
