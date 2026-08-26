"""WSGI entry point.

Local commands use development settings by default. Hosted deployments must set
DJANGO_SETTINGS_MODULE=auction_platform.settings.production.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'auction_platform.settings.development',
)
application = get_wsgi_application()
