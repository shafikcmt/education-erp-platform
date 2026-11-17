"""Anonymous and session-only authentication endpoints (plan §6.1 to §6.5, §8).

These views are on the reviewed allow-list of the URL authorization audit: they are either
anonymous by design (enumeration-safe, throttled, CSRF-protected) or need only an authenticated
session (logout, step-up)."""

from typing import Any

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.hosts import PLATFORM_AND_TENANT
from apps.identity import session_state as state
from apps.identity.api import serializers as s
from apps.identity.api.utils import CsrfProtectedView, service_errors
from apps.identity.models import User
from apps.identity.permissions import IsAuthenticatedSession
from apps.identity.services import accounts, auth

TAGS = ["auth"]
_ACCEPTED = {"detail": "If the account is eligible, an email is on its way."}


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(CsrfProtectedView):
    permission_classes = [AllowAny]
    host_classes = PLATFORM_AND_TENANT
    tenant_auth_flow = True  # reaches the view without the membership gate (D7)

    @extend_schema(tags=TAGS, summary="Set the CSRF cookie", responses=s.CsrfSerializer)
    def get(self, request: Request) -> Response:
        return Response({"detail": "ok"})


class LoginView(CsrfProtectedView):
    permission_classes = [AllowAny]
    host_classes = PLATFORM_AND_TENANT
    tenant_auth_flow = True  # reaches the view without the membership gate (D7)

    @extend_schema(
        tags=TAGS,
        summary="Sign in with email and password",
        request=s.LoginSerializer,
        responses=s.LoginResultSerializer,
    )
    def post(self, request: Request) -> Response:
        data = s.LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = auth.login_with_password(
            request._request, data.validated_data["email"], data.validated_data["password"]
        )
        return Response({"status": result.status.value})


class MfaVerifyView(CsrfProtectedView):
    permission_classes = [AllowAny]
    host_classes = PLATFORM_AND_TENANT
    tenant_auth_flow = True  # reaches the view without the membership gate (D7)

    @extend_schema(
        tags=TAGS,
        summary="Complete sign-in with a TOTP or recovery code",
        request=s.MfaVerifySerializer,
        responses=s.LoginResultSerializer,
    )
    def post(self, request: Request) -> Response:
        data = s.MfaVerifySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        auth.verify_mfa(
            request._request,
            code=data.validated_data.get("code", ""),
            recovery_code=data.validated_data.get("recovery_code", ""),
        )
        return Response({"status": "authenticated"})


class LogoutView(CsrfProtectedView):
    permission_classes = [IsAuthenticatedSession]
    host_classes = PLATFORM_AND_TENANT
    tenant_auth_flow = True  # ending one's own session is always allowed
    allow_during_mfa_enrollment = True

    @extend_schema(tags=TAGS, summary="Sign out", request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        auth.logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class StepUpView(CsrfProtectedView):
    permission_classes = [IsAuthenticatedSession]
    allow_during_mfa_enrollment = True

    @extend_schema(
        tags=TAGS,
        summary="Re-authenticate for sensitive actions (10 minutes)",
        request=s.StepUpSerializer,
        responses=s.StepUpResultSerializer,
    )
    def post(self, request: Request) -> Response:
        data = s.StepUpSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = request.user
        assert isinstance(user, User)  # noqa: S101 - IsAuthenticatedSession guarantees it
        auth.step_up(
            request._request,
            user,
            password=data.validated_data["password"],
            code=data.validated_data.get("code", ""),
            recovery_code=data.validated_data.get("recovery_code", ""),
        )
        return Response({"step_up_expires_at": state.step_up_expires_at(request._request)})


class PasswordResetView(CsrfProtectedView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=TAGS,
        summary="Request a password reset email (always 202)",
        request=s.EmailRequestSerializer,
        responses={202: s.AcceptedSerializer},
    )
    def post(self, request: Request) -> Response:
        data = s.EmailRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        accounts.request_password_reset(request._request, data.validated_data["email"])
        return Response(_ACCEPTED, status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(CsrfProtectedView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=TAGS,
        summary="Set a new password with a reset token (signs out everywhere)",
        request=s.TokenPasswordSerializer,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        data = s.TokenPasswordSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with service_errors():
            accounts.confirm_password_reset(
                request._request, data.validated_data["token"], data.validated_data["password"]
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivateView(CsrfProtectedView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=TAGS,
        summary="Activate an account and set the first password",
        request=s.TokenPasswordSerializer,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        data = s.TokenPasswordSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with service_errors():
            accounts.activate(
                request._request, data.validated_data["token"], data.validated_data["password"]
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivationResendView(CsrfProtectedView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=TAGS,
        summary="Resend the activation email (always 202)",
        request=s.EmailRequestSerializer,
        responses={202: s.AcceptedSerializer},
    )
    def post(self, request: Request) -> Response:
        data = s.EmailRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        accounts.request_activation_resend(request._request, data.validated_data["email"])
        return Response(_ACCEPTED, status=status.HTTP_202_ACCEPTED)


class EmailVerifyView(CsrfProtectedView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=TAGS,
        summary="Confirm an email change",
        request=s.TokenSerializer,
        responses={204: None},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        data = s.TokenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        accounts.verify_email_change(request._request, data.validated_data["token"])
        return Response(status=status.HTTP_204_NO_CONTENT)
