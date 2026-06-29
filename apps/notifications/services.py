"""
GhanaHammer Notifications Service
Channels: Email, WhatsApp (Meta Business API), In-App, SMS
"""
import logging
import requests
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


class NotificationService:
    """Central notification dispatcher"""

    # ─── In-App Notification Model ────────────────────────────────

    @staticmethod
    def create_in_app(user, title, message, notification_type='info', auction=None, url=''):
        from apps.notifications.models import Notification
        notif = Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            auction=auction,
            action_url=url,
        )
        # Push via WebSocket
        NotificationService._push_ws(user, notif)
        return notif

    @staticmethod
    def _push_ws(user, notification):
        """Push real-time notification via Django Channels"""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            group_name = f'notifications_{user.id}'
            async_to_sync(channel_layer.group_send)(group_name, {
                'type': 'notification',
                'data': {
                    'id': str(notification.id),
                    'title': notification.title,
                    'message': notification.message,
                    'type': notification.notification_type,
                    'url': notification.action_url,
                    'created_at': notification.created_at.isoformat(),
                }
            })
        except Exception as e:
            logger.debug(f'WS push skipped (likely InMemory layer in dev): {e}')

    # ─── Bid Events ───────────────────────────────────────────────

    @staticmethod
    def notify_outbid(user, auction, new_amount):
        title = f'You\'ve been outbid on {auction.lot_number}'
        message = f'Someone bid GHS {new_amount:,.2f} on "{auction.title}". Bid now to stay in!'
        url = auction.get_absolute_url()
        NotificationService.create_in_app(user, title, message, 'warning', auction, url)
        if user.email_notifications:
            NotificationService._send_email(
                user, f'Outbid Alert — {auction.lot_number}',
                'notifications/email/outbid.html',
                {'user': user, 'auction': auction, 'new_amount': new_amount}
            )
        if user.whatsapp_notifications and user.phone:
            NotificationService._send_whatsapp(
                user.phone,
                f'🔔 *GhanaHammer Alert*\nYou\'ve been outbid on *{auction.title}* (Lot {auction.lot_number}).\n'
                f'Current price: GHS {new_amount:,.2f}\nBid now: https://ghanahammer.com{url}'
            )

    @staticmethod
    def notify_auction_won(user, auction, amount):
        title = f'🎉 Congratulations! You won {auction.lot_number}'
        message = f'You won "{auction.title}" for GHS {amount:,.2f}. Please proceed to payment.'
        NotificationService.create_in_app(user, title, message, 'success', auction)
        if user.email_notifications:
            NotificationService._send_email(
                user, f'You Won! — {auction.lot_number}',
                'notifications/email/won.html',
                {'user': user, 'auction': auction, 'amount': amount}
            )
        if user.whatsapp_notifications and user.phone:
            NotificationService._send_whatsapp(
                user.phone,
                f'🏆 *Congratulations {user.first_name}!*\n\nYou won *{auction.title}* for GHS {amount:,.2f}!\n'
                f'Please complete your payment within 48 hours to secure your item.\n\n'
                f'Pay now: https://ghanahammer.com/payments/checkout/{auction.id}/'
            )

    @staticmethod
    def notify_seller_sale(user, auction, amount):
        title = f'Your item sold! {auction.lot_number}'
        message = f'"{auction.title}" sold for GHS {amount:,.2f}. Payment is in escrow.'
        NotificationService.create_in_app(user, title, message, 'success', auction)
        if user.email_notifications:
            NotificationService._send_email(
                user, f'Item Sold — {auction.lot_number}',
                'notifications/email/sold.html',
                {'user': user, 'auction': auction, 'amount': amount}
            )
        if user.whatsapp_notifications and user.phone:
            NotificationService._send_whatsapp(
                user.phone,
                f'💰 *Sale Alert!*\n\nYour item *{auction.title}* sold for GHS {amount:,.2f}.\n'
                f'Funds will be released from escrow once the buyer confirms receipt.'
            )

    @staticmethod
    def notify_payment_success(user, payment):
        title = 'Payment Successful'
        message = f'GHS {payment.amount_ghs:,.2f} payment confirmed. Funds are in secure escrow.'
        NotificationService.create_in_app(user, title, message, 'success')

    @staticmethod
    def notify_auto_bid_placed(user, auction, amount):
        title = f'Auto-bid placed — {auction.lot_number}'
        message = f'Your auto-bid of GHS {amount:,.2f} was placed on "{auction.title}".'
        NotificationService.create_in_app(user, title, message, 'info', auction)

    @staticmethod
    def notify_auto_bid_exhausted(user, auction, max_amount):
        title = f'Auto-bid limit reached — {auction.lot_number}'
        message = f'Your max auto-bid of GHS {max_amount:,.2f} has been exceeded. Bid manually to stay in!'
        NotificationService.create_in_app(user, title, message, 'warning', auction)
        if user.whatsapp_notifications and user.phone:
            NotificationService._send_whatsapp(
                user.phone,
                f'⚠️ *Auto-bid exhausted!*\nYour max limit of GHS {max_amount:,.2f} was exceeded on '
                f'*{auction.title}*.\nBid now: https://ghanahammer.com{auction.get_absolute_url()}'
            )

    # ─── Auction Ending Reminders ─────────────────────────────────

    @staticmethod
    def notify_ending_soon(user, auction):
        title = f'Ending soon — {auction.lot_number}'
        remaining = auction.time_remaining
        mins = int(remaining.total_seconds() // 60) if remaining else 0
        message = f'"{auction.title}" ends in ~{mins} minutes. Current price: GHS {auction.current_price:,.2f}'
        NotificationService.create_in_app(user, title, message, 'warning', auction)

    # ─── New Listing Alert ────────────────────────────────────────

    @staticmethod
    def notify_new_matching_item(user, auction, saved_search):
        title = f'New item matching "{saved_search.name}"'
        message = f'New listing: "{auction.title}" starting at GHS {auction.starting_price:,.2f}'
        NotificationService.create_in_app(user, title, message, 'info', auction)

    # ─── Email Sender ─────────────────────────────────────────────

    @staticmethod
    def _send_email(user, subject, template, context):
        try:
            html = render_to_string(template, context)
            send_mail(
                subject=f'[GhanaHammer] {subject}',
                message='',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html,
                fail_silently=True,
            )
        except Exception as e:
            logger.exception(f'Email send error: {e}')

    # ─── WhatsApp Sender ──────────────────────────────────────────

    @staticmethod
    def _send_whatsapp(phone, text):
        """Send WhatsApp message via Meta Business API"""
        if not settings.WHATSAPP_API_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
            logger.debug('WhatsApp not configured, skipping.')
            return

        # Normalize phone number (Ghana: +233xxxxxxxxx)
        phone = phone.strip().replace(' ', '').replace('-', '')
        if phone.startswith('0'):
            phone = '+233' + phone[1:]
        elif not phone.startswith('+'):
            phone = '+233' + phone

        url = f'https://graph.facebook.com/v18.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages'
        payload = {
            'messaging_product': 'whatsapp',
            'to': phone,
            'type': 'text',
            'text': {'preview_url': False, 'body': text},
        }
        headers = {
            'Authorization': f'Bearer {settings.WHATSAPP_API_TOKEN}',
            'Content-Type': 'application/json',
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code not in (200, 201):
                logger.warning(f'WhatsApp error {resp.status_code}: {resp.text[:200]}')
        except requests.RequestException as e:
            logger.exception(f'WhatsApp send error: {e}')
