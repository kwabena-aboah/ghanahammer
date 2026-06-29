"""
GhanaHammer Payment Models
Paystack integration: cards, bank transfers, mobile money
Escrow system for high-value item protection
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class Payment(models.Model):
    """Core payment record for any transaction"""
    
    TYPE_BID_WIN = 'bid_win'
    TYPE_BUY_NOW = 'buy_now'
    TYPE_SUBSCRIPTION = 'subscription'
    TYPE_CREDITS = 'bid_credits'
    TYPE_FEATURED = 'featured_listing'
    TYPE_DEPOSIT = 'deposit'
    TYPE_CHOICES = [
        (TYPE_BID_WIN, 'Auction Win Payment'),
        (TYPE_BUY_NOW, 'Buy Now Payment'),
        (TYPE_SUBSCRIPTION, 'Subscription Plan'),
        (TYPE_CREDITS, 'Bid Credits'),
        (TYPE_FEATURED, 'Featured Listing Fee'),
        (TYPE_DEPOSIT, 'Security Deposit'),
    ]
    
    CHANNEL_CARD = 'card'
    CHANNEL_BANK = 'bank_transfer'
    CHANNEL_MOMO_MTN = 'mtn_momo'
    CHANNEL_MOMO_TELECEL = 'telecel_cash'
    CHANNEL_MOMO_AIRTELTIGO = 'airteltigo_money'
    CHANNEL_CHOICES = [
        (CHANNEL_CARD, 'Card (Visa/Mastercard/Credit)'),
        (CHANNEL_BANK, 'Bank Transfer'),
        (CHANNEL_MOMO_MTN, 'MTN Mobile Money'),
        (CHANNEL_MOMO_TELECEL, 'Telecel Cash'),
        (CHANNEL_MOMO_AIRTELTIGO, 'AirtelTigo Money'),
    ]
    
    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_ABANDONED = 'abandoned'
    STATUS_REVERSED = 'reversed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_ABANDONED, 'Abandoned'),
        (STATUS_REVERSED, 'Reversed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payments')
    auction = models.ForeignKey(
        'gh_auctions.Auction', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments'
    )
    payment_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    channel = models.CharField(max_length=30, choices=CHANNEL_CHOICES, blank=True)
    amount_ghs = models.DecimalField(max_digits=14, decimal_places=2)
    platform_fee_ghs = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_to_seller_ghs = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    
    # Paystack
    paystack_reference = models.CharField(max_length=100, unique=True, blank=True)
    paystack_access_code = models.CharField(max_length=100, blank=True)
    paystack_transaction_id = models.CharField(max_length=100, blank=True)
    paystack_response = models.JSONField(default=dict, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Mobile Money specific
    momo_number = models.CharField(max_length=15, blank=True)
    momo_network = models.CharField(max_length=20, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gh_payments'
        ordering = ['-created_at']

    def __str__(self):
        return f"GHS {self.amount_ghs} - {self.get_payment_type_display()} - {self.status}"

    def save(self, *args, **kwargs):
        from decimal import Decimal
        if not self.paystack_reference:
            import random
            import string

            self.paystack_reference = 'GH-' + ''.join(
                random.choices(
                    string.ascii_uppercase + string.digits,
                    k=16
                )
            )

        amount = Decimal(str(self.amount_ghs))

        fee_rate = Decimal(str(settings.PLATFORM_COMMISSION_PERCENT)) / Decimal('100')

        self.platform_fee_ghs = amount * fee_rate
        self.net_to_seller_ghs = amount - self.platform_fee_ghs

        super().save(*args, **kwargs)


class EscrowAccount(models.Model):
    """Escrow fund holding for auction payments"""
    
    STATUS_HOLDING = 'holding'
    STATUS_RELEASED = 'released'
    STATUS_DISPUTED = 'disputed'
    STATUS_REFUNDED = 'refunded'
    STATUS_CHOICES = [
        (STATUS_HOLDING, 'Holding'),
        (STATUS_RELEASED, 'Released to Seller'),
        (STATUS_DISPUTED, 'Under Dispute'),
        (STATUS_REFUNDED, 'Refunded to Buyer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name='escrow')
    auction = models.ForeignKey('gh_auctions.Auction', on_delete=models.PROTECT, related_name='escrow')
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='escrow_as_buyer'
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='escrow_as_seller'
    )
    amount_ghs = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_HOLDING)
    
    # Buyer confirms receipt
    buyer_confirmed = models.BooleanField(default=False)
    buyer_confirmed_at = models.DateTimeField(null=True, blank=True)
    
    # Auto-release date
    auto_release_date = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
    
    # Dispute
    dispute_reason = models.TextField(blank=True)
    dispute_raised_at = models.DateTimeField(null=True, blank=True)
    dispute_resolved_at = models.DateTimeField(null=True, blank=True)
    dispute_resolution = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gh_escrow'

    def __str__(self):
        return f"Escrow GHS {self.amount_ghs} - {self.status}"

    def save(self, *args, **kwargs):
        if not self.auto_release_date:
            self.auto_release_date = timezone.now() + timezone.timedelta(
                days=settings.ESCROW_RELEASE_DAYS
            )
        super().save(*args, **kwargs)

    def release_to_seller(self):
        """Release escrow funds to seller"""
        self.status = self.STATUS_RELEASED
        self.released_at = timezone.now()
        self.save(update_fields=['status', 'released_at'])
        # TODO: Trigger actual Paystack payout to seller

    def raise_dispute(self, reason):
        self.status = self.STATUS_DISPUTED
        self.dispute_reason = reason
        self.dispute_raised_at = timezone.now()
        self.save(update_fields=['status', 'dispute_reason', 'dispute_raised_at'])


class BankTransferInstruction(models.Model):
    """Manual bank transfer instructions for buyers who pay by bank"""
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE)
    bank_name = models.CharField(max_length=100, default='Ghana Commercial Bank')
    account_name = models.CharField(max_length=200, default='GhanaHammer Ltd Escrow')
    account_number = models.CharField(max_length=30)
    branch = models.CharField(max_length=100, blank=True)
    sort_code = models.CharField(max_length=20, blank=True)
    reference_code = models.CharField(max_length=50)
    amount_ghs = models.DecimalField(max_digits=14, decimal_places=2)
    payment_confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        db_table = 'gh_bank_transfers'


class PaystackWebhookLog(models.Model):
    """Log all incoming Paystack webhooks"""
    event = models.CharField(max_length=100)
    reference = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gh_paystack_webhooks'
