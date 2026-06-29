"""
GhanaHammer Auction Views
Homepage, listing, detail, create/edit, search, watchlist toggle
"""
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q, Count, Avg, Sum
from django.conf import settings
from django.utils import timezone
from django.core.paginator import Paginator
from django.utils.dateparse import parse_datetime

from apps.gh_auctions.models import Auction, Category, AuctionImage, Watchlist, AuctionQuestion, BulkImportBatch
from apps.bidding.models import Bid

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HOMEPAGE
# ─────────────────────────────────────────────────────────────────────────────

def home(request):
    """Main homepage"""
    now = timezone.now()

    live_auctions = Auction.objects.filter(
        status__in=['active', 'extended'],
        auction_type='live',
    ).select_related('category', 'seller').prefetch_related('images')[:8]

    featured_auctions = Auction.objects.filter(
        status__in=['active', 'extended', 'preview'],
        is_featured=True,
    ).select_related('category', 'seller').prefetch_related('images')[:8]

    ending_soon = Auction.objects.filter(
        status__in=['active', 'extended'],
        end_time__lte=now + timezone.timedelta(hours=24),
    ).order_by('end_time').select_related('category').prefetch_related('images')[:8]

    new_arrivals = Auction.objects.filter(
        status__in=['active', 'scheduled'],
    ).order_by('-created_at').select_related('category').prefetch_related('images')[:8]

    top_categories = Category.objects.filter(
        is_active=True, parent=None
    ).annotate(
        auction_count=Count('auctions', filter=Q(auctions__status__in=['active', 'extended']))
    ).order_by('-auction_count')[:12]

    # Platform stats
    total_auctions = Auction.objects.filter(status__in=['active', 'extended', 'scheduled']).count()
    from django.contrib.auth import get_user_model
    User = get_user_model()
    total_users_count = User.objects.filter(is_active=True).count()
    total_volume = Auction.objects.filter(
        status='sold', winning_bid_amount__isnull=False
    ).aggregate(total=Sum('winning_bid_amount'))['total'] or 0

    # Watchlist IDs for card rendering
    watchlist_ids = set()
    if request.user.is_authenticated:
        watchlist_ids = set(str(w) for w in Watchlist.objects.filter(
            user=request.user
        ).values_list('auction_id', flat=True))

    return render(request, 'gh_auctions/home.html', {
        'live_auctions': live_auctions,
        'featured_auctions': featured_auctions,
        'ending_soon': ending_soon,
        'new_arrivals': new_arrivals,
        'top_categories': top_categories,
        'total_auctions': total_auctions,
        'total_users': total_users_count,
        'total_volume': int(total_volume),
        'watchlist_ids': watchlist_ids,
        'plans': settings.AUCTION_SUBSCRIPTION_PLANS,
    })


# ─────────────────────────────────────────────────────────────────────────────
# AUCTION LIST / SEARCH
# ─────────────────────────────────────────────────────────────────────────────

def auction_list(request):
    """Browse/search with filters"""
    qs = Auction.objects.filter(
        status__in=['active', 'extended', 'closing', 'preview', 'scheduled']
    ).select_related('category', 'seller').prefetch_related('images')

    # VIP preview: only Gold/Platinum can see preview status
    if not (request.user.is_authenticated and request.user.can_early_access):
        qs = qs.exclude(status='preview')

    # ── Filters ──────────────────────────────────────────────────
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(lot_number__icontains=q))

    category_slug = request.GET.get('category', '')
    if category_slug:
        try:
            cat = Category.objects.get(slug=category_slug)
            qs = qs.filter(Q(category=cat) | Q(category__parent=cat))
        except Category.DoesNotExist:
            pass

    auction_type = request.GET.get('type', '')
    if auction_type:
        qs = qs.filter(auction_type=auction_type)

    condition = request.GET.get('condition', '')
    if condition:
        qs = qs.filter(condition=condition)

    location = request.GET.get('location', '').strip()
    if location:
        qs = qs.filter(Q(location__icontains=location) | Q(region__icontains=location))

    region = request.GET.get('region', '').strip()
    if region:
        qs = qs.filter(region__icontains=region)

    min_price = request.GET.get('min_price', '')
    if min_price:
        try:
            qs = qs.filter(current_price__gte=float(min_price))
        except ValueError:
            pass

    max_price = request.GET.get('max_price', '')
    if max_price:
        try:
            qs = qs.filter(current_price__lte=float(max_price))
        except ValueError:
            pass

    seller_verified = request.GET.get('verified_seller', '')
    if seller_verified:
        qs = qs.filter(seller__is_verified_seller=True)

    featured_only = request.GET.get('featured', '')
    if featured_only:
        qs = qs.filter(is_featured=True)

    # ── Sort ──────────────────────────────────────────────────────
    sort = request.GET.get('sort', 'featured')
    sort_options = {
        'featured': ['-is_featured', '-is_sponsored', '-created_at'],
        'ending_soon': ['end_time'],
        'newest': ['-created_at'],
        'price_low': ['current_price'],
        'price_high': ['-current_price'],
        'most_bids': ['-bid_count'],
        'most_viewed': ['-view_count'],
    }
    qs = qs.order_by(*sort_options.get(sort, ['-created_at']))

    # Paginate
    paginator = Paginator(qs, 24)
    page = paginator.get_page(request.GET.get('page', 1))

    # Track watchlist IDs
    watchlist_ids = set()
    if request.user.is_authenticated:
        watchlist_ids = set(str(w) for w in Watchlist.objects.filter(
            user=request.user
        ).values_list('auction_id', flat=True))

    categories = Category.objects.filter(is_active=True, parent=None)

    return render(request, 'gh_auctions/list.html', {
        'page': page,
        'auctions': page.object_list,
        'total_count': paginator.count,
        'categories': categories,
        'watchlist_ids': watchlist_ids,
        'current_filters': {
            'q': q, 'category': category_slug, 'type': auction_type,
            'condition': condition, 'location': location, 'region': region,
            'min_price': min_price, 'max_price': max_price,
            'sort': sort,
        },
    })


# ─────────────────────────────────────────────────────────────────────────────
# AUCTION DETAIL
# ─────────────────────────────────────────────────────────────────────────────

def auction_detail(request, slug):
    """Auction detail page — increment view count, hydrate Vue app"""
    auction = get_object_or_404(
        Auction.objects.select_related('seller', 'category', 'winner')
                       .prefetch_related('images', 'documents', 'questions__asker'),
        slug=slug
    )

    # Increment view count (simple, non-unique for now)
    Auction.objects.filter(pk=auction.pk).update(view_count=auction.view_count + 1)

    # Check watchlist
    is_watching = False
    if request.user.is_authenticated:
        is_watching = Watchlist.objects.filter(user=request.user, auction=auction).exists()

    # Recent bids for Vue hydration
    recent_bids = list(
        Bid.objects.filter(auction=auction)
        .select_related('bidder')
        .order_by('-placed_at')[:20]
        .values('bidder__first_name', 'bidder__last_name', 'bidder__username',
                'amount', 'placed_at', 'source')
    )
    recent_bids_data = []
    for b in recent_bids:
        name = f"{b['bidder__first_name']} {b['bidder__last_name']}".strip() or b['bidder__username']
        # Partially mask name for privacy
        parts = name.split()
        if len(parts) > 1:
            masked = f"{parts[0]} {parts[-1][0]}."
        else:
            masked = name[:3] + '***'
        recent_bids_data.append({
            'bidder': masked,
            'amount': str(b['amount']),
            'placed_at': b['placed_at'].isoformat(),
            'source': b['source'],
        })

    # Related auctions
    related_auctions = Auction.objects.filter(
        category=auction.category,
        status__in=['active', 'extended'],
    ).exclude(pk=auction.pk).prefetch_related('images')[:4]

    return render(request, 'gh_auctions/detail.html', {
        'auction': auction,
        'is_seller': request.user.is_authenticated and request.user == auction.seller,
        'is_watching': is_watching,
        'related_auctions': related_auctions,
        'recent_bids_json': json.dumps(recent_bids_data),
        'sniper_minutes': settings.AUCTION_SNIPER_EXTENSION_MINUTES,
    })


# ─────────────────────────────────────────────────────────────────────────────
# CREATE / EDIT AUCTION
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def auction_create(request):
    """Create new auction listing"""
    if request.method == 'POST':
        return _save_auction(request, auction=None)

    categories = Category.objects.filter(is_active=True).order_by('name')
    regions = [
        'Greater Accra', 'Ashanti', 'Western', 'Central', 'Eastern',
        'Volta', 'Northern', 'Upper East', 'Upper West', 'Brong-Ahafo',
        'Oti', 'Bono', 'Bono East', 'Ahafo', 'North East', 'Savannah',
    ]
    return render(request, 'gh_auctions/create_edit.html', {
        'categories': categories,
        'form': {},
        'regions': regions,
    })


@login_required
def auction_edit(request, slug):
    """Edit existing auction (seller only, draft/scheduled only)"""
    auction = get_object_or_404(Auction, slug=slug, seller=request.user)
    if auction.status not in ['draft', 'scheduled']:
        messages.error(request, 'Active auctions cannot be edited once bidding has started.')
        return redirect('auction_detail', slug=auction.slug)

    if request.method == 'POST':
        return _save_auction(request, auction=auction)

    categories = Category.objects.filter(is_active=True).order_by('name')
    regions = [
        'Greater Accra', 'Ashanti', 'Western', 'Central', 'Eastern',
        'Volta', 'Northern', 'Upper East', 'Upper West', 'Brong-Ahafo',
        'Oti', 'Bono', 'Bono East', 'Ahafo', 'North East', 'Savannah',
    ]
    return render(request, 'gh_auctions/create_edit.html', {
        'auction': auction,
        'categories': categories,
        'form': auction,
        'regions': regions,
    })


def _save_auction(request, auction=None):
    """Save auction from POST data"""
    from decimal import Decimal
    data = request.POST
    action = data.get('action', 'publish')

    # Validate required fields
    required = ['title', 'category', 'description', 'starting_price', 'start_time', 'end_time']
    for field in required:
        if not data.get(field):
            messages.error(request, f'Field "{field}" is required.')
            return redirect(request.path)

    try:
        category = Category.objects.get(id=data['category'])
    except Category.DoesNotExist:
        messages.error(request, 'Invalid category selected.')
        return redirect(request.path)

    start_time = parse_datetime(data['start_time'])
    end_time = parse_datetime(data['end_time'])

    if not start_time or not end_time:
        messages.error(request, 'Invalid date/time format.')
        return redirect(request.path)

    if end_time <= start_time:
        messages.error(request, 'End time must be after start time.')
        return redirect(request.path)

    starting_price = Decimal(data['starting_price'])
    reserve_price = Decimal(data['reserve_price']) if data.get('reserve_price') else None
    buy_now_price = Decimal(data['buy_now_price']) if data.get('buy_now_price') else None
    bid_increment = Decimal(data.get('bid_increment', '10'))

    status = 'draft' if action == 'draft' else ('scheduled' if start_time > timezone.now() else 'active')

    # Check plan limits
    if status != 'draft':
        plan = settings.AUCTION_SUBSCRIPTION_PLANS.get(request.user.plan, {})
        max_listings = plan.get('max_listings', 5)
        if max_listings != -1:
            active_count = Auction.objects.filter(
                seller=request.user, status__in=['active', 'scheduled', 'preview']
            ).count()
            if active_count >= max_listings:
                messages.error(request, f'Your {request.user.plan} plan allows {max_listings} active listings. Please upgrade.')
                return redirect('dashboard_subscription')

    if auction:
        # Update existing
        auction.title = data['title']
        auction.category = category
        auction.description = data['description']
        auction.condition = data.get('condition', 'used')
        auction.auction_type = data.get('auction_type', 'standard')
        auction.starting_price = starting_price
        auction.current_price = starting_price if not auction.bid_count else auction.current_price
        auction.reserve_price = reserve_price
        auction.buy_now_price = buy_now_price
        auction.bid_increment = bid_increment
        auction.start_time = start_time
        auction.end_time = end_time
        auction.location = data.get('location', '')
        auction.region = data.get('region', '')
        auction.shipping_available = bool(data.get('shipping_available'))
        auction.pickup_only = bool(data.get('pickup_only'))
        auction.shipping_cost = Decimal(data['shipping_cost']) if data.get('shipping_cost') else None
        auction.status = status
        auction.save()
    else:
        auction = Auction.objects.create(
            seller=request.user,
            title=data['title'],
            category=category,
            description=data['description'],
            condition=data.get('condition', 'used'),
            auction_type=data.get('auction_type', 'standard'),
            starting_price=starting_price,
            current_price=starting_price,
            reserve_price=reserve_price,
            buy_now_price=buy_now_price,
            bid_increment=bid_increment,
            start_time=start_time,
            end_time=end_time,
            preview_start=parse_datetime(data['preview_start']) if data.get('preview_start') else None,
            location=data.get('location', ''),
            region=data.get('region', ''),
            shipping_available=bool(data.get('shipping_available')),
            pickup_only=bool(data.get('pickup_only')),
            shipping_cost=Decimal(data['shipping_cost']) if data.get('shipping_cost') else None,
            status=status,
        )
        request.user.total_listings += 1
        request.user.save(update_fields=['total_listings'])

    # Save images
    images = request.FILES.getlist('images')
    for i, img_file in enumerate(images[:settings.AUCTION_MAX_IMAGES_PER_LISTING]):
        AuctionImage.objects.create(
            auction=auction,
            image=img_file,
            is_primary=(i == 0 and not auction.images.exists()),
            sort_order=i,
        )

    if status == 'draft':
        messages.success(request, f'Auction saved as draft. Lot #{auction.lot_number}')
        return redirect('dashboard_my_auctions')
    else:
        messages.success(request, f'Auction published successfully! Lot #{auction.lot_number}')
        return redirect('auction_detail', slug=auction.slug)


# ─────────────────────────────────────────────────────────────────────────────
# WATCHLIST
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def toggle_watchlist(request, auction_id):
    """Toggle watchlist status for an auction"""
    auction = get_object_or_404(Auction, id=auction_id)
    watch, created = Watchlist.objects.get_or_create(user=request.user, auction=auction)
    if not created:
        watch.delete()
        Auction.objects.filter(pk=auction.pk).update(
            watchlist_count=auction.watchlist_count - 1
        )
        return JsonResponse({'watching': False})
    else:
        Auction.objects.filter(pk=auction.pk).update(
            watchlist_count=auction.watchlist_count + 1
        )
        return JsonResponse({'watching': True})


# ─────────────────────────────────────────────────────────────────────────────
# QUESTIONS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def ask_question(request, slug):
    auction = get_object_or_404(Auction, slug=slug)
    question_text = request.POST.get('question', '').strip()
    if question_text and request.user != auction.seller:
        AuctionQuestion.objects.create(
            auction=auction,
            asker=request.user,
            question=question_text,
        )
        messages.success(request, 'Question submitted. The seller will respond shortly.')
    return redirect('auction_detail', slug=slug)


# ─────────────────────────────────────────────────────────────────────────────
# BULK IMPORT
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def bulk_import(request):
    """CSV/Excel bulk listing upload"""
    if request.method == 'POST':
        file = request.FILES.get('import_file')
        if not file:
            messages.error(request, 'Please select a file.')
            return redirect('bulk_import')

        ext = file.name.lower().split('.')[-1]
        if ext not in ['csv', 'xlsx', 'xls']:
            messages.error(request, 'Only CSV and Excel files (.csv, .xlsx, .xls) are supported.')
            return redirect('bulk_import')

        batch = BulkImportBatch.objects.create(
            seller=request.user,
            file=file,
        )
        # Queue Celery task
        from apps.gh_auctions.tasks import process_bulk_import
        process_bulk_import.delay(str(batch.id))

        messages.success(request, f'File uploaded. Processing started (Batch #{batch.id}). Check back shortly.')
        return redirect('dashboard_my_auctions')

    return render(request, 'gh_auctions/bulk_import.html', {
        'recent_batches': BulkImportBatch.objects.filter(seller=request.user).order_by('-created_at')[:10],
    })


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT PROCESSOR
# ─────────────────────────────────────────────────────────────────────────────

def auction_context(request):
    """Inject global nav data into all templates"""
    categories = Category.objects.filter(is_active=True, parent=None).order_by('sort_order', 'name')[:12]
    return {
        'nav_categories': categories,
        'sniper_minutes': settings.AUCTION_SNIPER_EXTENSION_MINUTES,
        'paystack_public_key': settings.PAYSTACK_PUBLIC_KEY,
    }
