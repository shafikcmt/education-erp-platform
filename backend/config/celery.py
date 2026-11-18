"""Celery application.

Every task is declared as a platform task (``apps.core.tasking.platform_task``) or a tenant
task (``apps.tenancy.tasking.tenant_task``), which takes ``tenant_id`` explicitly and runs in
that tenant's transaction (ADR-009, Phase 3 M7).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("erp")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
