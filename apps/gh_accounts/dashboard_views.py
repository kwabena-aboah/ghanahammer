"""apps/accounts/dashboard_views.py — Seller/Buyer Dashboard"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q
from django.conf import settings
from django.utils import timezone


@login_required
def dashboard_home(request):
    """Main dashboard overview"""
    user = request.user
    from apps.gh_auctions.models import Auction, Watchlist
    from apps.bidding.models import Bid, AutoBid
    from apps.payments.models import EscrowAccount, Payment
    from apps.notifications.models import Notification

    # Buyer stats
    active_bids = Bid.objects.filter(
        bidder=user, status=Bid.STATUS_WINNING,
        auction__status__in=['active', 'extended', 'closing']
    ).select_related('auction').count()

    won_auctions = Bid.objects.filter(bidder=user, status=Bid.STATUS_WON).count()
    watchlist_count = Watchlist.objects.filter(user=user).count()

    # Seller stats
    active_listings = Auction.objects.filter(
        seller=user, status__in=['active', 'extended', 'preview', 'scheduled']
    ).count()

    total_revenue = Auction.objects.filter(
        seller=user, status='sold'
    ).aggregate(total=Sum('winning_bid_amount'))['total'] or 0

    # Pending payments (won but not paid)
    pending_payments = Auction.objects.filter(
        winner=user,
        status='sold',
    ).exclude(
        payments__status='success'
    ).count()

    # Escrow items needing attention
    escrow_pending = EscrowAccount.objects.filter(
        buyer=user,
        status=EscrowAccount.STATUS_HOLDING,
        buyer_confirmed=False,
    ).count()

    # Recent notifications
    notifications = Notification.objects.filter(
        user=user, is_read=False
    ).order_by('-created_at')[:5]

    # Ending soon - auctions user is winning
    ending_soon_bids = Bid.objects.filter(
        bidder=user,
        status=Bid.STATUS_WINNING,
        auction__status__in=['active', 'extended'],
        auction__end_time__lte=timezone.now() + timezone.timedelta(hours=6),
    ).select_related('auction').order_by('auction__end_time')[:5]

    # Recent activity feed
    recent_bids = Bid.objects.filter(
        bidder=user
    ).select_related('auction').order_by('-placed_at')[:5]

    # Plan info
    plan = settings.AUCTION_SUBSCRIPTION_PLANS.get(user.plan, {})
    max_listings = plan.get('max_listings', 5)
    listings_used = Auction.objects.filter(
        seller=user,
        status__in=['active', 'extended', 'preview', 'scheduled']
    ).count()

    return render(request, 'dashboard/home.html', {
        'active_bids': active_bids,
        'won_auctions': won_auctions,
        'watchlist_count': watchlist_count,
        'active_listings': active_listings,
        'total_revenue': total_revenue,
        'pending_payments': pending_payments,
        'escrow_pending': escrow_pending,
        'notifications': notifications,
        'ending_soon_bids': ending_soon_bids,
        'recent_bids': recent_bids,
        'max_listings': max_listings,
        'listings_used': listings_used,
        'listings_pct': int(listings_used / max(max_listings, 1) * 100) if max_listings != -1 else 0,
    })


@login_required
def my_bids(request):
    """All bids placed by the user"""
    from apps.bidding.models import Bid, AutoBid

    status_filter = request.GET.get('status', '')
    bids = Bid.objects.filter(bidder=request.user).select_related(
        'auction', 'auction__category', 'auction__seller'
    ).prefetch_related('auction__images').order_by('-placed_at')

    if status_filter:
        bids = bids.filter(status=status_filter)

    # Auto-bids
    auto_bids = AutoBid.objects.filter(
        bidder=request.user,
        status=AutoBid.STATUS_ACTIVE,
    ).select_related('auction').order_by('-created_at')

    paginator = Paginator(bids, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'dashboard/my_bids.html', {
        'page': page,
        'bids': page.object_list,
        'auto_bids': auto_bids,
        'status_filter': status_filter,
        'bid_statuses': Bid.STATUS_CHOICES,
        'total_count': paginator.count,
    })


@login_required
def my_auctions(request):
    """Seller's own auction listings"""
    from apps.gh_auctions.models import Auction, BulkImportBatch

    status_filter = request.GET.get('status', '')
    auctions = Auction.objects.filter(seller=request.user).select_related(
        'category'
    ).prefetch_related('images').order_by('-created_at')

    if status_filter:
        auctions = auctions.filter(status=status_filter)

    # Stats
    stats = auctions.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status__in=['active', 'extended'])),
        sold=Count('id', filter=Q(status='sold')),
        draft=Count('id', filter=Q(status='draft')),
        revenue=Sum('winning_bid_amount', filter=Q(status='sold')),
    )

    # Recent bulk imports
    bulk_batches = BulkImportBatch.objects.filter(
        seller=request.user
    ).order_by('-created_at')[:5]

    paginator = Paginator(auctions, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'dashboard/my_auctions.html', {
        'page': page,
        'auctions': page.object_list,
        'stats': stats,
        'status_filter': status_filter,
        'status_choices': Auction.STATUS_CHOICES,
        'bulk_batches': bulk_batches,
        'total_count': paginator.count,
    })


@login_required
def watchlist(request):
    """User's watchlist"""
    from apps.gh_auctions.models import Watchlist as WatchlistModel

    watches = WatchlistModel.objects.filter(
        user=request.user
    ).select_related(
        'auction', 'auction__category', 'auction__seller'
    ).prefetch_related('auction__images').order_by('-added_at')

    paginator = Paginator(watches, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'dashboard/watchlist.html', {
        'page': page,
        'watches': page.object_list,
        'total_count': paginator.count,
    })


@login_required
def purchases(request):
    """Won auctions and their payment/escrow status"""
    from apps.gh_auctions.models import Auction
    from apps.payments.models import Payment, EscrowAccount

    won_auctions = Auction.objects.filter(
        winner=request.user
    ).select_related('seller').prefetch_related('images', 'payments').order_by('-updated_at')

    # Enrich with payment and escrow data
    purchase_list = []
    for auction in won_auctions:
        payment = auction.payments.filter(
            payment_type__in=[Payment.TYPE_BID_WIN, Payment.TYPE_BUY_NOW]
        ).first()
        escrow = None
        if payment and hasattr(payment, 'escrow'):
            escrow = payment.escrow

        purchase_list.append({
            'auction': auction,
            'payment': payment,
            'escrow': escrow,
            'needs_payment': not payment or payment.status != Payment.STATUS_SUCCESS,
        })

    return render(request, 'dashboard/purchases.html', {
        'purchases': purchase_list,
    })


@login_required
def analytics_redirect(request):
    """Redirect to seller analytics"""
    return redirect('seller_analytics')


@login_required
def subscription_page(request):
    """Subscription plan management page"""
    from apps.bidding.models import BidCreditPackage
    from apps.payments.models import Payment

    credit_packages = BidCreditPackage.objects.filter(is_active=True).order_by('sort_order')
    recent_subscriptions = Payment.objects.filter(
        user=request.user
    ).order_by('-created_at')[:5] if hasattr(Payment, 'objects') else []

    return render(request, 'dashboard/subscription.html', {
        'credit_packages': credit_packages,
        'recent_subscriptions': recent_subscriptions,
        'plans': settings.AUCTION_SUBSCRIPTION_PLANS,
    })


@login_required
def saved_searches(request):
    """Manage saved searches / smart alerts"""
    from apps.gh_accounts.models import SavedSearch
    from apps.gh_auctions.models import Category

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            SavedSearch.objects.create(
                user=request.user,
                name=request.POST.get('name', 'My Search'),
                query=request.POST.get('query', ''),
                category=request.POST.get('category', ''),
                min_price=request.POST.get('min_price') or None,
                max_price=request.POST.get('max_price') or None,
                location=request.POST.get('location', ''),
                condition=request.POST.get('condition', ''),
                alert_new_items=bool(request.POST.get('alert_new_items')),
                alert_price_drops=bool(request.POST.get('alert_price_drops')),
                alert_ending_soon=bool(request.POST.get('alert_ending_soon')),
            )
            messages.success(request, 'Saved search created. You will receive alerts when matching items are listed.')
            return redirect('dashboard_saved_searches')

        elif action == 'delete':
            search_id = request.POST.get('search_id')
            SavedSearch.objects.filter(id=search_id, user=request.user).delete()
            messages.success(request, 'Saved search removed.')
            return redirect('dashboard_saved_searches')

        elif action == 'toggle':
            search_id = request.POST.get('search_id')
            search = SavedSearch.objects.filter(id=search_id, user=request.user).first()
            if search:
                search.is_active = not search.is_active
                search.save(update_fields=['is_active'])

    searches = SavedSearch.objects.filter(user=request.user).order_by('-created_at')
    categories = Category.objects.filter(is_active=True).values('slug', 'name')

    return render(request, 'dashboard/saved_searches.html', {
        'searches': searches,
        'categories': categories,
    })


@login_required
def messages_inbox(request):
    """In-app messaging inbox"""
    from apps.messaging.models import MessageThread

    threads = MessageThread.objects.filter(
        participants=request.user
    ).select_related('auction').order_by('-updated_at')

    return render(request, 'dashboard/messages.html', {
        'threads': threads,
    })


@login_required
def account_settings(request):
    """Account settings - notifications, security, payment preferences"""
    user = request.user
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'notifications':
            user.whatsapp_notifications = bool(request.POST.get('whatsapp_notifications'))
            user.email_notifications = bool(request.POST.get('email_notifications'))
            user.sms_notifications = bool(request.POST.get('sms_notifications'))
            user.save(update_fields=['whatsapp_notifications', 'email_notifications', 'sms_notifications'])
            messages.success(request, 'Notification preferences saved.')

        elif action == 'payment':
            user.momo_number = request.POST.get('momo_number', '').strip()
            user.momo_network = request.POST.get('momo_network', '')
            user.save(update_fields=['momo_number', 'momo_network'])
            messages.success(request, 'Payment preferences saved.')

        return redirect('dashboard_settings')

    return render(request, 'dashboard/settings.html', {'user': user})
