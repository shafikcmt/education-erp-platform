"""Stable Problem Details errors of the tenancy services (plan §12.4)."""

from rest_framework import status

from apps.core.exceptions import ProblemError


class InvitationInvalid(ProblemError):
    """One answer for unknown, expired, used and revoked tokens (no oracle)."""

    status_code = status.HTTP_400_BAD_REQUEST
    problem_code = "invitation_invalid"
    title = "Invitation not valid"
    default_detail = "This invitation is not valid any more. Ask for a new one."


class InvitationEmailMismatch(ProblemError):
    status_code = status.HTTP_403_FORBIDDEN
    problem_code = "invitation_email_mismatch"
    title = "Different account"
    default_detail = "This invitation was sent to a different, verified email address."


class InvitationRateLimited(ProblemError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    problem_code = "rate_limited"
    title = "Too many requests"
    default_detail = "Too many invitations. Please wait and try again."


class TenantHostsDisabled(ProblemError):
    status_code = status.HTTP_409_CONFLICT
    problem_code = "tenant_hosts_disabled"
    title = "Tenant hosts are disabled"
    default_detail = "Tenants can't be provisioned while tenant hosts are disabled."


class LimitExceededError(ProblemError):
    status_code = status.HTTP_403_FORBIDDEN
    problem_code = "limit_exceeded"
    title = "Limit reached"
    default_detail = "The organisation's institution or campus limit is reached."
