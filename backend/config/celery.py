"""Celery application. Queues are fixed here; tasks choose a queue via routing or `queue=`."""

import os

from celery import Celery
from kombu import Exchange, Queue

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

QUEUE_NAMES = ("default", "critical", "bulk", "notifications", "integrations")

app = Celery("npms", task_cls="kernel.foundation.tasks:BaseTask")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.task_queues = tuple(Queue(name, Exchange(name), routing_key=name) for name in QUEUE_NAMES)
app.conf.task_default_queue = "default"
app.conf.task_default_exchange = "default"
app.conf.task_default_routing_key = "default"
app.autodiscover_tasks()
