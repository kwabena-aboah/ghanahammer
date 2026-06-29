"""
GhanaHammer Auction Models
Core auction listings, categories, watchlists, lot management
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse
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


class Category(models.Model):
    """Auction item categories"""
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    icon = models.CharField(max_length=50, blank=True, help_text='Bootstrap icon class e.g. bi-car-front')
    image = models.ImageField(upload_to='categories/', null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'gh_categories'
        verbose_name_plural = 'Categories'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Auction(models.Model):
    """Core auction listing"""
    
    TYPE_STANDARD = 'standard'     # Normal auction
    TYPE_RESERVE = 'reserve'       # Reserve price
    TYPE_BUY_NOW = 'buy_now'       # Auction + Buy Now option
    TYPE_LIVE = 'live'             # Live video auction
    TYPE_SEALED = 'sealed'         # Sealed bids (highest wins)
    AUCTION_TYPES = [
        (TYPE_STANDARD, 'Standard Auction'),
        (TYPE_RESERVE, 'Reserve Price Auction'),
        (TYPE_BUY_NOW, 'Buy Now + Auction'),
        (TYPE_LIVE, 'Live Auction'),
        (TYPE_SEALED, 'Sealed Bid Auction'),
    ]
    
    STATUS_DRAFT = 'draft'
    STATUS_SCHEDULED = 'scheduled'
    STATUS_PREVIEW = 'preview'     # VIP early access phase
    STATUS_ACTIVE = 'active'
    STATUS_EXTENDED = 'extended'   # Bid sniper extension active
    STATUS_CLOSING = 'closing'     # Within last 5 minutes
    STATUS_ENDED = 'ended'
    STATUS_SOLD = 'sold'
    STATUS_UNSOLD = 'unsold'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SCHEDULED, 'Scheduled'),
        (STATUS_PREVIEW, 'VIP Preview'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_EXTENDED, 'Extended (Anti-Snipe)'),
        (STATUS_CLOSING, 'Closing Soon'),
        (STATUS_ENDED, 'Ended'),
        (STATUS_SOLD, 'Sold'),
        (STATUS_UNSOLD, 'Unsold'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    
    CONDITION_NEW = 'new'
    CONDITION_USED = 'used'
    CONDITION_REFURBISHED = 'refurbished'
    CONDITION_FOR_PARTS = 'for_parts'
    CONDITION_CHOICES = [
        (CONDITION_NEW, 'New'),
        (CONDITION_USED, 'Used'),
        (CONDITION_REFURBISHED, 'Refurbished'),
        (CONDITION_FOR_PARTS, 'For Parts / Not Working'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lot_number = models.CharField(max_length=20, unique=True, blank=True)
    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=350, unique=True, blank=True)
    description = models.TextField()
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='auctions'
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='auctions')
    auction_type = models.CharField(max_length=20, choices=AUCTION_TYPES, default=TYPE_STANDARD)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default=CONDITION_USED)
    
    # Pricing
    starting_price = models.DecimalField(max_digits=14, decimal_places=2)
    current_price = models.DecimalField(max_digits=14, decimal_places=2)
    reserve_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    buy_now_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    bid_increment = models.DecimalField(max_digits=10, decimal_places=2, default=10.00)
    
    # Timing
    preview_start = models.DateTimeField(null=True, blank=True, help_text='VIP early access start')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    original_end_time = models.DateTimeField(null=True, blank=True)  # Before any sniper extensions
    
    # Location
    location = models.CharField(max_length=300, blank=True)
    region = models.CharField(max_length=100, blank=True)
    
    # Visibility & Promotion
    is_featured = models.BooleanField(default=False)
    is_sponsored = models.BooleanField(default=False)
    is_vip_only = models.BooleanField(default=False)
    featured_until = models.DateTimeField(null=True, blank=True)
    
    # Stats
    view_count = models.PositiveIntegerField(default=0)
    watchlist_count = models.PositiveIntegerField(default=0)
    bid_count = models.PositiveIntegerField(default=0)
    
    # Winner
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='won_auctions'
    )
    winning_bid_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    reserve_met = models.BooleanField(default=False)
    
    # AI-generated metadata
    ai_suggested_start_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    ai_suggested_reserve = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    ai_suggested_buy_now = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    ai_demand_score = models.FloatField(null=True, blank=True)
    
    # Live auction
    stream_url = models.URLField(blank=True)
    stream_key = models.CharField(max_length=200, blank=True)
    
    # Shipping & Pickup
    shipping_available = models.BooleanField(default=False)
    pickup_only = models.BooleanField(default=False)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Bulk listing reference
    bulk_import_batch = models.CharField(max_length=100, blank=True)
    
    history = HistoricalRecords()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gh_auctions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'end_time']),
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['is_featured', 'status']),
        ]

    def __str__(self):
        return f"[{self.lot_number}] {self.title}"

    def save(self, *args, **kwargs):
        if not self.lot_number:
            import random, string
            self.lot_number = 'GH' + ''.join(random.choices(string.digits, k=6))
        if not self.slug:
            base_slug = slugify(self.title)
            self.slug = f"{base_slug}-{self.lot_number.lower()}"
        if not self.current_price:
            self.current_price = self.starting_price
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('auction_detail', kwargs={'slug': self.slug})

    @property
    def is_active(self):
        return self.status in [self.STATUS_ACTIVE, self.STATUS_EXTENDED, self.STATUS_CLOSING]

    @property
    def time_remaining(self):
        if self.end_time > timezone.now():
            return self.end_time - timezone.now()
        return None

    @property
    def is_reserve_met(self):
        if not self.reserve_price:
            return True
        return self.current_price >= self.reserve_price

    @property
    def min_next_bid(self):
        return self.current_price + self.bid_increment

    def extend_for_sniper(self):
        """Extend auction end time for bid-sniper protection"""
        extension = timezone.timedelta(minutes=settings.AUCTION_SNIPER_EXTENSION_MINUTES)
        if not self.original_end_time:
            self.original_end_time = self.end_time
        self.end_time = timezone.now() + extension
        self.status = self.STATUS_EXTENDED
        self.save(update_fields=['end_time', 'original_end_time', 'status'])


class AuctionImage(models.Model):
    """Multiple images per auction listing"""
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='auction_images/%Y/%m/')
    caption = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    ai_enhanced = models.BooleanField(default=False)

    class Meta:
        db_table = 'gh_auction_images'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"Image for {self.auction.lot_number}"


class AuctionDocument(models.Model):
    """Supporting documents for listings (e.g. vehicle papers, certificates)"""
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='auction_docs/%Y/%m/')
    is_public = models.BooleanField(default=False, help_text='Visible to all or only verified bidders')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gh_auction_documents'


class Watchlist(models.Model):
    """Users can watch auctions to get alerts"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='watchlist')
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name='watchers')
    alert_outbid = models.BooleanField(default=True)
    alert_ending_soon = models.BooleanField(default=True)
    alert_price_change = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gh_watchlist'
        unique_together = ['user', 'auction']


class AuctionQuestion(models.Model):
    """Buyer questions about a listing"""
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name='questions')
    asker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField(blank=True)
    is_public = models.BooleanField(default=True)
    asked_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'gh_auction_questions'


class BulkImportBatch(models.Model):
    """Track bulk CSV/Excel listing imports"""
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    file = models.FileField(upload_to='bulk_imports/')
    total_rows = models.PositiveIntegerField(default=0)
    imported = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[('processing', 'Processing'), ('done', 'Done'), ('failed', 'Failed')],
        default='processing'
    )
    error_log = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gh_bulk_imports'
