"""
GhanaHammer Accounts Models
User profiles, subscriptions, verification badges
"""
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
try:
    from simple_history.models import HistoricalRecords
    _history_available = True
except ImportError:
    _history_available = False
    # Stub so models don't break if simple_history not installed
    class HistoricalRecords:
        def __init__(self, *a, **kw): pass
        def contribute_to_class(self, *a, **kw): pass
        def __set_name__(self, *a, **kw): pass

import uuid


class User(AbstractUser):
    """Extended user model for GhanaHammer"""
    
    ROLE_BUYER = 'buyer'
    ROLE_SELLER = 'seller'
    ROLE_BOTH = 'both'
    ROLE_AUCTIONEER = 'auctioneer'
    ROLE_CHOICES = [
        (ROLE_BUYER, 'Buyer'),
        (ROLE_SELLER, 'Seller'),
        (ROLE_BOTH, 'Buyer & Seller'),
        (ROLE_AUCTIONEER, 'Professional Auctioneer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_BOTH)
    
    # Profile
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio = models.TextField(blank=True)
    company_name = models.CharField(max_length=200, blank=True)
    location = models.CharField(max_length=200, blank=True)
    region = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    
    # Verification
    is_verified_seller = models.BooleanField(default=False)
    kyc_status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('submitted', 'Submitted'), ('verified', 'Verified'), ('rejected', 'Rejected')],
        default='pending'
    )
    
    # 2FA
    two_factor_enabled = models.BooleanField(default=False)
    totp_secret = models.CharField(max_length=32, blank=True)
    
    # Stats
    total_bids = models.PositiveIntegerField(default=0)
    total_wins = models.PositiveIntegerField(default=0)
    total_listings = models.PositiveIntegerField(default=0)
    seller_rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.00)
    
    # Preferences
    whatsapp_notifications = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    
    # Momo / Payment Info
    momo_number = models.CharField(max_length=15, blank=True)
    momo_network = models.CharField(
        max_length=20,
        choices=[('mtn', 'MTN MoMo'), ('telecel', 'Telecel Cash'), ('airteltigo', 'AirtelTigo Money')],
        blank=True
    )
    
    history = HistoricalRecords()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        db_table = 'gh_users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    @property
    def full_name(self):
        return self.get_full_name() or self.username

    @property
    def is_plan_active(self):
        return True

    @property
    def can_early_access(self):
        return True

    @property
    def has_analytics(self):
        return self.is_staff

    def get_seller_badge(self):
        if self.is_verified_seller:
            return 'verified'
        elif self.seller_rating >= 4.5:
            return 'trusted'
        return None


class SavedSearch(models.Model):
    """Saved search queries for smart alerts"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_searches')
    name = models.CharField(max_length=100)
    query = models.CharField(max_length=500, blank=True)
    category = models.CharField(max_length=100, blank=True)
    min_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    condition = models.CharField(max_length=50, blank=True)
    alert_new_items = models.BooleanField(default=True)
    alert_price_drops = models.BooleanField(default=True)
    alert_ending_soon = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_alerted = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'gh_saved_searches'

    def __str__(self):
        return f"{self.user.email} - {self.name}"



class SellerReview(models.Model):
    """Reviews for sellers"""
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_reviews')
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_reviews')
    auction = models.ForeignKey('gh_auctions.Auction', on_delete=models.SET_NULL, null=True, blank=True)
    rating = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gh_seller_reviews'
        unique_together = ['reviewer', 'seller', 'auction']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update seller's average rating
        avg = SellerReview.objects.filter(seller=self.seller).aggregate(
            avg=models.Avg('rating')
        )['avg']
        if avg:
            self.seller.seller_rating = round(avg, 2)
            self.seller.save(update_fields=['seller_rating'])
