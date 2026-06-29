"""apps/payments/urls.py"""
from django.urls import path
from apps.payments import views
from apps.payments.subscription_views import subscription_checkout

urlpatterns = [
    path('checkout/<uuid:auction_id>/', views.checkout, name='checkout'),
    path('callback/', views.payment_callback, name='payment_callback'),
    path('momo-otp/', views.momo_otp_submit, name='momo_otp_submit'),
    path('escrow/<uuid:pk>/', views.escrow_detail, name='escrow_detail'),
    path('escrow/<uuid:pk>/confirm/', views.confirm_receipt, name='confirm_receipt'),
    path('escrow/<uuid:pk>/dispute/', views.raise_dispute, name='raise_dispute'),
    path('webhook/paystack/', views.paystack_webhook, name='paystack_webhook'),
    path('subscription/', subscription_checkout, name='subscription_checkout'),
]
