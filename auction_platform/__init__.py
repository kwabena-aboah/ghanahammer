# Import Celery app so it's ready when Django starts
import pymysql

try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    pass  # Celery not installed in this environment


pymysql.install_as_MySQLdb()