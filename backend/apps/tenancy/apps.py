from django.apps import AppConfig


class TenancyConfig(AppConfig):
    """`tenancy` module: tenants, institutions, campuses, domains, memberships (Phase 3)."""

    name = "apps.tenancy"
    label = "tenancy"
    verbose_name = "Tenancy"
