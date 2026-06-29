"""apps/kyc/urls.py"""
from django.urls import path
from apps.kyc.views import kyc_overview, kyc_submit

urlpatterns = [
    path('', kyc_overview, name='kyc_overview'),
    path('submit/', kyc_submit, name='kyc_submit'),
]
