from django.apps import AppConfig


class IdentityConfig(AppConfig):
    """`identity` module. Phase 1 holds only the custom User model (set before the first
    migration, as Django requires). Login, MFA, sessions and invitations arrive in Phase 2."""

    name = "apps.identity"
    label = "identity"
    verbose_name = "Identity"
