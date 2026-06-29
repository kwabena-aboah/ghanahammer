"""apps/accounts/views.py — Profile, 2FA"""
import pyotp
import qrcode
import io
import base64
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings


@login_required
def profile(request):
    user = request.user
    from apps.gh_accounts.models import SellerReview
    reviews = SellerReview.objects.filter(seller=user).select_related('reviewer', 'auction').order_by('-created_at')[:10]
    return render(request, 'accounts/profile.html', {'profile_user': user, 'reviews': reviews})


@login_required
def edit_profile(request):
    user = request.user
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.phone = request.POST.get('phone', user.phone)
        user.bio = request.POST.get('bio', user.bio)
        user.company_name = request.POST.get('company_name', user.company_name)
        user.location = request.POST.get('location', user.location)
        user.region = request.POST.get('region', user.region)
        user.momo_number = request.POST.get('momo_number', user.momo_number)
        user.momo_network = request.POST.get('momo_network', user.momo_network)
        user.whatsapp_notifications = bool(request.POST.get('whatsapp_notifications'))
        user.email_notifications = bool(request.POST.get('email_notifications'))
        user.sms_notifications = bool(request.POST.get('sms_notifications'))

        if request.FILES.get('avatar'):
            user.avatar = request.FILES['avatar']

        user.save()
        messages.success(request, 'Profile updated successfully.')
        return redirect('profile')

    return render(request, 'accounts/edit_profile.html', {'user': user})


@login_required
def setup_2fa(request):
    """Set up TOTP two-factor authentication"""
    user = request.user

    if request.method == 'POST':
        otp = request.POST.get('otp_code', '')
        secret = request.session.get('totp_secret_temp')
        if not secret:
            messages.error(request, 'Session expired. Please try again.')
            return redirect('setup_2fa')

        totp = pyotp.TOTP(secret)
        if totp.verify(otp):
            user.totp_secret = secret
            user.two_factor_enabled = True
            user.save(update_fields=['totp_secret', 'two_factor_enabled'])
            del request.session['totp_secret_temp']
            messages.success(request, '2FA enabled successfully. Your account is now more secure.')
            return redirect('dashboard_settings')
        else:
            messages.error(request, 'Invalid OTP code. Please try again.')

    # Generate new TOTP secret
    secret = pyotp.random_base32()
    request.session['totp_secret_temp'] = secret

    totp = pyotp.TOTP(secret)
    provisioning_url = totp.provisioning_uri(
        name=user.email,
        issuer_name='GhanaHammer'
    )

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=6, border=4)
    qr.add_data(provisioning_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_b64 = base64.b64encode(buffer.getvalue()).decode()

    return render(request, 'accounts/setup_2fa.html', {
        'secret': secret,
        'qr_code': qr_b64,
    })


@login_required
def verify_2fa(request):
    """Verify 2FA during login (called from custom login flow)"""
    if request.method == 'POST':
        otp = request.POST.get('otp_code', '')
        user = request.user
        if user.two_factor_enabled and user.totp_secret:
            totp = pyotp.TOTP(user.totp_secret)
            if totp.verify(otp, valid_window=1):
                request.session['2fa_verified'] = True
                return redirect(request.POST.get('next', '/dashboard/'))
            messages.error(request, 'Invalid OTP. Please try again.')
    return render(request, 'accounts/verify_2fa.html')


@login_required
def disable_2fa(request):
    if request.method == 'POST':
        request.user.two_factor_enabled = False
        request.user.totp_secret = ''
        request.user.save(update_fields=['two_factor_enabled', 'totp_secret'])
        messages.success(request, '2FA has been disabled.')
    return redirect('dashboard_settings')
