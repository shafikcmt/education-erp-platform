from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Platform foundation module (`core`): ids, base models, errors, logging, health."""

    name = "apps.core"
    label = "core"
    verbose_name = "Core"
