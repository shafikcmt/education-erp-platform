"""Celery application.

Tasks that touch tenant data must accept ``tenant_id`` explicitly and re-establish tenant
context (ADR-009). The tenant-aware base task is delivered in Phase 3.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("erp")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
