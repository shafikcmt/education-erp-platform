"""Django project package. Importing the Celery app here makes ``@shared_task`` use it."""

from config.celery import app as celery_app

__all__ = ("celery_app",)
