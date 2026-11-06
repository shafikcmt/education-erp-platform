from django.apps import AppConfig


class RbacConfig(AppConfig):
    name = "apps.rbac"
    label = "rbac"
    verbose_name = "Roles and permissions"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.rbac import signals  # noqa: F401  (cache invalidation)
