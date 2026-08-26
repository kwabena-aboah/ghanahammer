"""Passenger entry point for Namecheap cPanel Python applications."""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Namecheap must run the hardened production settings.
os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'auction_platform.settings.production',
)

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
