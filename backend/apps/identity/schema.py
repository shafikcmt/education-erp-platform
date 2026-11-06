"""OpenAPI description of the session authentication class (cookie + CSRF, ADR-011)."""

from drf_spectacular.authentication import SessionScheme


class ErpSessionScheme(SessionScheme):  # type: ignore[no-untyped-call]
    target_class = "apps.identity.authentication.SessionAuthentication"
    name = "sessionAuth"
