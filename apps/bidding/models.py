"""
GhanaHammer Bidding Models
Bids, auto-bidding, bid credits, fraud flags
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class Bid(models.Model):
    """Individual bid placed on an auction"""
    
    STATUS_ACTIVE = 'active'
    STATUS_OUTBID = 'outbid'
    STATUS_WINNING = 'winning'
    STATUS_WON = 'won'
    STATUS_CANCELLED = 'cancelled'
    STATUS_RETRACTED = 'retracted'
    STATUS_FRAUD = 'fraud'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_OUTBID, 'Outbid'),
        (STATUS_WINNING, 'Winning'),
        (STATUS_WON, 'Won'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_RETRACTED, 'Retracted'),
        (STATUS_FRAUD, 'Flagged as Fraud'),
    ]
    
    SOURCE_MANUAL = 'manual'
    SOURCE_AUTO = 'auto'          # Placed by auto-bidder
    SOURCE_BUY_NOW = 'buy_now'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Manual Bid'),
        (SOURCE_AUTO, 'Auto-Bid'),
        (SOURCE_BUY_NOW, 'Buy Now'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    auction = models.ForeignKey('gh_auctions.Auction', on_delete=models.PROTECT, related_name='bids')
    bidder = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='bids')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    
    # Anti-fraud metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    fraud_score = models.FloatField(default=0.0)
    fraud_flags = models.JSONField(default=list)
    
    # Bid sniper: was this bid placed in the final window?
    triggered_extension = models.BooleanField(default=False)
    
    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gh_bids'
        ordering = ['-placed_at']
        indexes = [
            models.Index(fields=['auction', 'status']),
            models.Index(fields=['bidder', 'status']),
            models.Index(fields=['auction', '-amount']),
        ]

    def __str__(self):
        return f"GHS {self.amount} on {self.auction.lot_number} by {self.bidder.username}"


class AutoBid(models.Model):
    """Proxy/auto-bidding configuration per user per auction"""
    
    STATUS_ACTIVE = 'active'
    STATUS_EXHAUSTED = 'exhausted'   # Max limit reached
    STATUS_WON = 'won'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_EXHAUSTED, 'Max Limit Reached'),
        (STATUS_WON, 'Won Auction'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    auction = models.ForeignKey('gh_auctions.Auction', on_delete=models.CASCADE, related_name='auto_bids')
    bidder = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='auto_bids')
    max_amount = models.DecimalField(max_digits=14, decimal_places=2)
    current_auto_bid = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gh_auto_bids'
        unique_together = ['auction', 'bidder']

    def __str__(self):
        return f"AutoBid: {self.bidder.username} max GHS {self.max_amount} on {self.auction.lot_number}"


class BidCreditPackage(models.Model):
    """Purchasable bid credit packs"""
    name = models.CharField(max_length=100)
    credits = models.PositiveIntegerField()
    price_ghs = models.DecimalField(max_digits=10, decimal_places=2)
    bonus_credits = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'gh_bid_credit_packages'
        ordering = ['sort_order']

    def __str__(self):
        total = self.credits + self.bonus_credits
        return f"{total} credits for GHS {self.price_ghs}"


class BidCreditTransaction(models.Model):
    """Log of bid credit purchases and usage"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='credit_transactions')
    amount = models.IntegerField(help_text='Positive = credit, Negative = debit')
    description = models.CharField(max_length=200)
    bid = models.ForeignKey(Bid, on_delete=models.SET_NULL, null=True, blank=True)
    package = models.ForeignKey(BidCreditPackage, on_delete=models.SET_NULL, null=True, blank=True)
    balance_after = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gh_credit_transactions'


class FraudFlag(models.Model):
    """AI / rule-based fraud detection flags"""
    
    FLAG_SHILL = 'shill_bidding'
    FLAG_MULTI_ACCOUNT = 'multi_account'
    FLAG_VELOCITY = 'bid_velocity'
    FLAG_PATTERN = 'suspicious_pattern'
    FLAG_ACCOUNT = 'account_suspicious'
    FLAG_TYPES = [
        (FLAG_SHILL, 'Shill Bidding'),
        (FLAG_MULTI_ACCOUNT, 'Multiple Accounts'),
        (FLAG_VELOCITY, 'Abnormal Bid Velocity'),
        (FLAG_PATTERN, 'Suspicious Bidding Pattern'),
        (FLAG_ACCOUNT, 'Suspicious Account Activity'),
    ]
    
    SEVERITY_LOW = 'low'
    SEVERITY_MEDIUM = 'medium'
    SEVERITY_HIGH = 'high'
    SEVERITY_CRITICAL = 'critical'

    bid = models.ForeignKey(Bid, on_delete=models.CASCADE, null=True, blank=True, related_name='fraud_flags_detail')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='fraud_flags')
    auction = models.ForeignKey('gh_auctions.Auction', on_delete=models.CASCADE, null=True, blank=True)
    flag_type = models.CharField(max_length=50, choices=FLAG_TYPES)
    severity = models.CharField(max_length=20, default=SEVERITY_MEDIUM)
    details = models.JSONField(default=dict)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resolved_flags'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'gh_fraud_flags'
