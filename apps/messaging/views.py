"""apps/messaging/views.py"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.messaging.models import MessageThread, Message


@login_required
def inbox(request):
    threads = MessageThread.objects.filter(participants=request.user).order_by('-updated_at')
    return render(request, 'messaging/inbox.html', {'threads': threads})


@login_required
def start_thread(request, seller_id, auction_id):
    from django.contrib.auth import get_user_model
    from apps.gh_auctions.models import Auction

    User = get_user_model()
    seller = get_object_or_404(User, id=seller_id)
    auction = get_object_or_404(Auction, id=auction_id)

    if seller == request.user:
        messages.error(request, 'You cannot message yourself.')
        return redirect('auction_detail', slug=auction.slug)

    # Find or create thread
    existing = MessageThread.objects.filter(
        participants=request.user, auction=auction
    ).filter(participants=seller).first()

    if existing:
        return redirect('messaging_thread', thread_id=existing.id)

    thread = MessageThread.objects.create(auction=auction)
    thread.participants.add(request.user, seller)

    if request.method == 'POST':
        content = request.POST.get('message', '').strip()
        if content:
            Message.objects.create(thread=thread, sender=request.user, content=content)

    return redirect('messaging_thread', thread_id=thread.id)


@login_required
def thread_detail(request, thread_id):
    thread = get_object_or_404(
        MessageThread.objects.prefetch_related('participants', 'messages__sender'),
        id=thread_id,
        participants=request.user,
    )

    if request.method == 'POST':
        content = request.POST.get('message', '').strip()
        offer = request.POST.get('offer_amount', '')
        if content:
            Message.objects.create(
                thread=thread,
                sender=request.user,
                content=content,
                offer_amount=offer if offer else None,
                message_type=Message.TYPE_OFFER if offer else Message.TYPE_TEXT,
            )
        return redirect('messaging_thread', thread_id=thread_id)

    # Mark messages as read
    thread.messages.exclude(sender=request.user).update(is_read=True)

    other_participant = thread.participants.exclude(id=request.user.id).first()

    return render(request, 'messaging/thread.html', {
        'thread': thread,
        'messages_list': thread.messages.order_by('created_at'),
        'other_participant': other_participant,
    })
