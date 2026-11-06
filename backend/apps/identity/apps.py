from django.apps import AppConfig


class IdentityConfig(AppConfig):
    """`identity` module: users, authentication, MFA, sessions and account flows (Phase 2).
    Tenant invitations arrive in Phase 3."""

    name = "apps.identity"
    label = "identity"
    verbose_name = "Identity"

    def ready(self) -> None:
        from apps.identity import schema  # noqa: F401  (registers the OpenAPI auth extension)
