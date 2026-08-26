from django.urls import path
from apps.gh_accounts.views import registration_disabled

urlpatterns = [
    path('', registration_disabled, name='account_signup'),
]
