"""Stable Problem Details errors of the authentication API (docs/API_STANDARDS.md §4)."""

from rest_framework import status

from apps.core.exceptions import ProblemError


class InvalidCredentials(ProblemError):
    """Same body for unknown email, wrong password, inactive and unactivated (no enumeration)."""

    status_code = status.HTTP_401_UNAUTHORIZED
    problem_code = "invalid_credentials"
    title = "Sign-in failed"
    default_detail = "The email address or password is incorrect."


class InvalidMfaCode(ProblemError):
    status_code = status.HTTP_401_UNAUTHORIZED
    problem_code = "invalid_mfa_code"
    title = "Verification failed"
    default_detail = "The verification code is incorrect or has expired."


class MfaChallengeExpired(ProblemError):
    status_code = status.HTTP_401_UNAUTHORIZED
    problem_code = "mfa_challenge_expired"
    title = "Sign-in expired"
    default_detail = "Please sign in again."


class RateLimited(ProblemError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    problem_code = "rate_limited"
    title = "Too many requests"
    default_detail = "Too many attempts. Please wait and try again."

    def __init__(self, retry_after: int) -> None:
        super().__init__(extra={"retry_after": retry_after})
        self.wait = retry_after


class StepUpRequired(ProblemError):
    status_code = status.HTTP_403_FORBIDDEN
    problem_code = "step_up_required"
    title = "Confirm it's you"
    default_detail = "Re-enter your password to continue."


class MfaRequired(ProblemError):
    status_code = status.HTTP_403_FORBIDDEN
    problem_code = "mfa_required"
    title = "Two-factor verification required"
    default_detail = "This action requires a session verified with two-factor authentication."


class MfaEnrollmentRequired(ProblemError):
    status_code = status.HTTP_403_FORBIDDEN
    problem_code = "mfa_enrollment_required"
    title = "Set up two-factor authentication"
    default_detail = "Your account must set up two-factor authentication before continuing."


class MfaRequiredForAccount(ProblemError):
    status_code = status.HTTP_409_CONFLICT
    problem_code = "mfa_required_for_account"
    title = "Two-factor authentication is mandatory"
    default_detail = "Two-factor authentication cannot be disabled for this account."


class ManualKeyAlreadyShown(ProblemError):
    status_code = status.HTTP_410_GONE
    problem_code = "manual_key_already_shown"
    title = "Key already shown"
    default_detail = "The setup key can be shown only once. Restart setup to get a new key."


class EnrollmentNotFound(ProblemError):
    status_code = status.HTTP_404_NOT_FOUND
    problem_code = "not_found"
    title = "Not found"
    default_detail = "No pending two-factor setup was found. Start setup again."


class InvalidToken(ProblemError):
    status_code = status.HTTP_400_BAD_REQUEST
    problem_code = "invalid_token"
    title = "Link invalid or expired"
    default_detail = "This link is invalid or has expired. Request a new one."


class GuardRail(ProblemError):
    status_code: int = status.HTTP_409_CONFLICT
    title = "Not allowed"

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.problem_code = code
