# Namecheap cPanel deployment

1. In cPanel, create a Python application using Python 3.11 or newer.
2. Set the application root to `/home/CPANEL_USER/ghanahammer`.
3. Upload the project into that directory.
4. Set the startup file to `passenger_wsgi.py` and entry point to `application`.
5. Copy `.env.example` to the project root as `.env` and fill in the real values.
6. Set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` to the real domain.
7. Create the cPanel MySQL database/user and set `DATABASE_URL`.
8. Install dependencies from `requirements.txt` in the cPanel virtualenv.
9. Run `python manage.py migrate --settings=auction_platform.settings.production`.
10. Run `python manage.py collectstatic --noinput --settings=auction_platform.settings.production`.
11. Create the administrator with `python manage.py createsuperuser --settings=auction_platform.settings.production`.
12. Copy `.htaccess.example` to the application root as `.htaccess` and replace `CPANEL_USER`.
13. Restart the Python application in cPanel.

The root `passenger_wsgi.py` always selects production settings. Local `manage.py`, WSGI,
and ASGI commands default to development settings unless `DJANGO_SETTINGS_MODULE` is set.

Namecheap shared hosting normally does not support Redis, WebSockets, or persistent Celery
workers. Use `USE_REDIS=False`; browsing and REST bidding work, while real-time updates,
auto-close jobs, and background tasks require a VPS or managed Redis/Celery service.
