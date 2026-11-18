from decouple import config, Csv
from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

# Production values are supplied by the hosting environment.
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Security headers
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Namecheap shared hosting may not provide Redis. Disable Redis explicitly there.
if not config('USE_REDIS', default='True', cast=bool):
    CHANNEL_LAYERS = {
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    }
    CACHES = {
        'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'},
    }
    CELERY_TASK_ALWAYS_EAGER = True

# Use Cloudflare R2 for media when its complete configuration is provided.
r2_settings = (
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_R2_ACCESS_KEY_ID,
    CLOUDFLARE_R2_SECRET_ACCESS_KEY,
    CLOUDFLARE_R2_BUCKET_NAME,
)
if any(r2_settings) and not all(r2_settings):
    raise ImproperlyConfigured(
        'Cloudflare R2 requires account ID, access key ID, secret access key, and bucket name.'
    )

if all(r2_settings):
    STORAGES = {
        **STORAGES,
        'default': {
            'BACKEND': 'storages.backends.s3.S3Storage',
            'OPTIONS': {
                'access_key': CLOUDFLARE_R2_ACCESS_KEY_ID,
                'secret_key': CLOUDFLARE_R2_SECRET_ACCESS_KEY,
                'bucket_name': CLOUDFLARE_R2_BUCKET_NAME,
                'endpoint_url': f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
                'region_name': 'auto',
                'default_acl': None,
                'querystring_auth': not bool(CLOUDFLARE_R2_PUBLIC_DOMAIN),
                'custom_domain': CLOUDFLARE_R2_PUBLIC_DOMAIN or None,
            },
        },
    }
