from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Platform foundation module (`core`): ids, base models, errors, logging, health,
    tenant context primitives (Phase 3)."""

    name = "apps.core"
    label = "core"
    verbose_name = "Core"

    def ready(self) -> None:
        from celery.signals import task_postrun, task_prerun
        from django.core.signals import request_finished, request_started
        from django.db import connections
        from django.db.backends.signals import connection_created

        from apps.core.tenancy import boundaries
        from apps.core.tenancy.transaction import install_query_guard

        # The tenant query guard on every database connection (ADR-042), including any that
        # were opened before the app registry finished loading.
        connection_created.connect(install_query_guard, dispatch_uid="erp.tenancy.guard")
        for conn in connections.all(initialized_only=True):
            install_query_guard(conn)

        request_started.connect(boundaries.on_request_started, dispatch_uid="erp.tenancy.rs")
        request_finished.connect(boundaries.on_request_finished, dispatch_uid="erp.tenancy.rf")
        task_prerun.connect(boundaries.on_task_prerun, dispatch_uid="erp.tenancy.tpre", weak=False)
        task_postrun.connect(
            boundaries.on_task_postrun, dispatch_uid="erp.tenancy.tpost", weak=False
        )
