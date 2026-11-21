from django.apps import AppConfig


class ModuleRegistryConfig(AppConfig):
    """`module_registry` module: module manifests, entitlements, feature flags (Phase 4)."""

    name = "apps.module_registry"
    label = "module_registry"
    verbose_name = "Module registry"
