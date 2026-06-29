"""GhanaHammer Auction Platform URL Configuration"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Auth
    path('accounts/', include('allauth.urls')),
    path('auth/', include('apps.gh_accounts.urls')),
    
    # Core Platform
    path('', include('apps.gh_auctions.urls')),
    path('payments/', include('apps.payments.urls')),
    path('messaging/', include('apps.messaging.urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('kyc/', include('apps.kyc.urls')),
    path('notifications/', include('apps.notifications.urls')),
    
    # Dashboard
    path('dashboard/', include('apps.gh_accounts.dashboard_urls')),
    
    # REST API
    path('api/v1/', include([
        path('accounts/', include('apps.gh_accounts.api_urls')),
        path('auctions/', include('apps.gh_auctions.api_urls')),
        path('bidding/', include('apps.bidding.api_urls')),
        path('payments/', include('apps.payments.api_urls')),
        path('messaging/', include('apps.messaging.api_urls')),
        path('analytics/', include('apps.analytics.api_urls')),
        path('ai/', include('apps.ai_engine.api_urls')),
    ])),
    
    # Pages
    path('about/', TemplateView.as_view(template_name='pages/about.html'), name='about'),
    path('how-it-works/', TemplateView.as_view(template_name='pages/how_it_works.html'), name='how_it_works'),
    path('terms/', TemplateView.as_view(template_name='pages/terms.html'), name='terms'),
    path('privacy/', TemplateView.as_view(template_name='pages/privacy.html'), name='privacy'),
    path('contact/', TemplateView.as_view(template_name='pages/contact.html'), name='contact'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Admin customization
admin.site.site_header = 'MachineAuction Admin'
admin.site.site_title = 'MachineAuction'
admin.site.index_title = 'Auction Platform Administration'
