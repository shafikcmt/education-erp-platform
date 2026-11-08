from django.apps import AppConfig


class IsolationProbeConfig(AppConfig):
    name = "tests.isolation_app"
    label = "isolation_probe"
    verbose_name = "Isolation probes (tests only)"
    default_auto_field = "django.db.models.BigAutoField"
