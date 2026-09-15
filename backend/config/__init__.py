"""Project configuration: settings, URL routing, ASGI/WSGI and Celery entrypoints."""

from .celery import app as celery_app

__all__ = ("celery_app",)
