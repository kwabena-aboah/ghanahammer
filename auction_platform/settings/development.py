from .base import *

DEBUG = True
ALLOWED_HOSTS = ['*']

# Use SQLite in dev
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# In-memory channel layer for dev (no Redis required)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

# Console email in dev
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Disable email verification in dev
ACCOUNT_EMAIL_VERIFICATION = 'none'

# Dummy cache in dev
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Celery eager in dev
CELERY_TASK_ALWAYS_EAGER = True

# INSTALLED_APPS += ['django_extensions']  # install django-extensions if needed
