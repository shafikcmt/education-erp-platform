"""Self-service account endpoints (/api/v1/me/...; plan §6.3 to §6.7, §8)."""

import uuid
from typing import Any

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.hosts import PLATFORM_AND_TENANT
from apps.identity import session_state as state
from apps.identity.api import serializers as s
from apps.identity.api.utils import CsrfProtectedView, get_or_404, service_errors
from apps.identity.models import RecoveryCode, User
from apps.identity.permissions import RequireStepUp
from apps.identity.services import accounts, mfa, sessions
from apps.rbac.engine import PLATFORM, ScopeTarget, effective_permissions, user_requires_mfa
from apps.rbac.permissions import HasPermission

TAGS = ["me"]
OWN_MFA = HasPermission("identity.mfa.manage_own")


def _user(request: Request) -> User:
    user = request.user
    assert isinstance(user, User)  # noqa: S101 - permission classes guarantee it
    return user


def _target(request: Request) -> ScopeTarget:
    return getattr(request._request, "scope_target", PLATFORM)


def me_payload(request: Request) -> dict[str, Any]:
    user = _user(request)
    django_request = request._request
    # Phase 3: on a tenant host, privileged tenant roles count too (any scope of the tenant).
    required = user_requires_mfa(user, target=_target(request))
    enabled = mfa.has_mfa(user)
    verified = state.mfa_verified(django_request)
    return {
        "id": user.pk,
        "email": user.email,
        "display_name": user.display_name,
        "locale": user.locale,
        "email_verified_at": user.email_verified_at,
        "mfa_enabled": enabled,
        "mfa_required": required,
        "mfa_enrollment_required": required and not enabled,
        "is_platform_staff": user.platform_roles.exists(),
        # Until MFA is complete, a privileged session sees only what it can actually use.
        "permissions": sorted(effective_permissions(user))
        if verified or not required
        else sorted(c for c in effective_permissions(user) if c.startswith("identity.")),
        "session": {
            "mfa_verified": verified,
            "idle_expires_at": state.idle_expires_at(django_request),
            "absolute_expires_at": state.absolute_expires_at(django_request),
            "step_up_expires_at": state.step_up_expires_at(django_request),
            "idle_timeout_seconds": settings.SESSION_IDLE_TIMEOUT_SECONDS,
        },
    }


class MeView(CsrfProtectedView):
    permission_classes = [
        HasPermission({"GET": "identity.account.view_own", "PATCH": "identity.account.update_own"})
    ]
    allow_during_mfa_enrollment = True
    host_classes = PLATFORM_AND_TENANT  # own account only; members pass the tenant gate first

    @extend_schema(
        tags=TAGS, summary="Current user, permissions and session", responses=s.MeSerializer
    )
    def get(self, request: Request) -> Response:
        return Response(s.MeSerializer(me_payload(request)).data)

    @extend_schema(
        tags=TAGS,
        summary="Update own profile",
        request=s.MeUpdateSerializer,
        responses=s.MeSerializer,
    )
    def patch(self, request: Request) -> Response:
        data = s.MeUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        accounts.update_profile(request._request, _user(request), data.validated_data)
        return Response(s.MeSerializer(me_payload(request)).data)


class PasswordChangeView(CsrfProtectedView):
    permission_classes = [HasPermission("identity.account.update_own"), RequireStepUp]

    @extend_schema(
        tags=TAGS,
        summary="Change password (step-up; signs out other sessions)",
        request=s.PasswordChangeSerializer,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        data = s.PasswordChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with service_errors():
            accounts.change_password(
                request._request,
                _user(request),
                current_password=data.validated_data["current_password"],
                new_password=data.validated_data["new_password"],
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmailChangeView(CsrfProtectedView):
    permission_classes = [HasPermission("identity.account.update_own"), RequireStepUp]

    @extend_schema(
        tags=TAGS,
        summary="Request an email change (step-up; verification link to the new address)",
        request=s.EmailChangeSerializer,
        responses={202: s.AcceptedSerializer},
    )
    def post(self, request: Request) -> Response:
        data = s.EmailChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with service_errors():
            accounts.request_email_change(
                request._request, _user(request), data.validated_data["new_email"]
            )
        return Response(
            {"detail": "Check the new address for a confirmation link."},
            status=status.HTTP_202_ACCEPTED,
        )


class MfaStatusView(CsrfProtectedView):
    # Phase 3 M8: tenant administrators enrol MFA on their tenant host (plan N47).
    host_classes = PLATFORM_AND_TENANT
    permission_classes = [OWN_MFA]
    allow_during_mfa_enrollment = True

    @extend_schema(tags=TAGS, summary="Own MFA status", responses=s.MfaStatusSerializer)
    def get(self, request: Request) -> Response:
        user = _user(request)
        device = mfa.confirmed_device(user)
        remaining = RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()
        return Response(
            {
                "enabled": device is not None,
                "is_required": user_requires_mfa(user, target=_target(request)),
                "confirmed_at": device.confirmed_at if device else None,
                "recovery_codes_remaining": remaining if device else 0,
            }
        )


class MfaSetupView(CsrfProtectedView):
    # Phase 3 M8: tenant administrators enrol MFA on their tenant host (plan N47).
    host_classes = PLATFORM_AND_TENANT
    permission_classes = [OWN_MFA]
    allow_during_mfa_enrollment = True

    @extend_schema(
        tags=TAGS,
        summary="Start TOTP enrollment (QR SVG only; replaces a pending enrollment)",
        request=None,
        responses={201: s.MfaSetupSerializer},
    )
    def post(self, request: Request) -> Response:
        enrollment = mfa.start_enrollment(_user(request), request=request._request)
        return Response(
            {
                "device_id": enrollment.device.pk,
                "qr_svg": enrollment.qr_svg_data_uri,
                "expires_at": enrollment.device.enrollment_expires_at,
            },
            status=status.HTTP_201_CREATED,
        )


class MfaManualKeyView(CsrfProtectedView):
    # Phase 3 M8: tenant administrators enrol MFA on their tenant host (plan N47).
    host_classes = PLATFORM_AND_TENANT
    permission_classes = [OWN_MFA]
    allow_during_mfa_enrollment = True

    @extend_schema(
        tags=TAGS,
        summary="Reveal the setup key once (fresh step-up; ADR-038)",
        request=None,
        responses=s.ManualKeySerializer,
    )
    def post(self, request: Request, device_id: str) -> Response:
        key = mfa.reveal_manual_key(_user(request), _uuid(device_id), request=request._request)
        return Response({"manual_key": key})


class MfaSetupCancelView(CsrfProtectedView):
    # Phase 3 M8: tenant administrators enrol MFA on their tenant host (plan N47).
    host_classes = PLATFORM_AND_TENANT
    permission_classes = [OWN_MFA]
    allow_during_mfa_enrollment = True

    @extend_schema(tags=TAGS, summary="Cancel a pending enrollment", responses={204: None})
    def delete(self, request: Request, device_id: str) -> Response:
        mfa.cancel_enrollment(_user(request), _uuid(device_id), request=request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MfaConfirmView(CsrfProtectedView):
    # Phase 3 M8: tenant administrators enrol MFA on their tenant host (plan N47).
    host_classes = PLATFORM_AND_TENANT
    permission_classes = [OWN_MFA]
    allow_during_mfa_enrollment = True

    @extend_schema(
        tags=TAGS,
        summary="Confirm enrollment with a code; returns recovery codes once",
        request=s.MfaConfirmSerializer,
        responses=s.RecoveryCodesSerializer,
    )
    def post(self, request: Request) -> Response:
        data = s.MfaConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        codes = mfa.confirm_enrollment(
            _user(request),
            data.validated_data["device_id"],
            data.validated_data["code"],
            request=request._request,
        )
        return Response({"recovery_codes": codes})


class MfaDisableView(CsrfProtectedView):
    permission_classes = [OWN_MFA, RequireStepUp]

    @extend_schema(
        tags=TAGS,
        summary="Turn off MFA (step-up; not for privileged accounts)",
        responses={204: None},
    )
    def delete(self, request: Request) -> Response:
        user = _user(request)
        mfa.disable_mfa(
            user,
            request=request._request,
            required=user_requires_mfa(user, target=_target(request)),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecoveryCodesView(CsrfProtectedView):
    # Phase 3 M8: tenant administrators enrol MFA on their tenant host (plan N47).
    host_classes = PLATFORM_AND_TENANT
    permission_classes = [OWN_MFA, RequireStepUp]

    @extend_schema(
        tags=TAGS,
        summary="Regenerate recovery codes (step-up; old codes stop working)",
        request=None,
        responses=s.RecoveryCodesSerializer,
    )
    def post(self, request: Request) -> Response:
        codes = mfa.regenerate_recovery_codes(_user(request), request=request._request)
        return Response({"recovery_codes": codes})


class SessionsView(CsrfProtectedView):
    permission_classes = [HasPermission("identity.session.view_own")]

    @extend_schema(
        tags=TAGS,
        summary="Own active sessions (masked IPs)",
        responses=s.SessionSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        records = sessions.active_sessions(_user(request))
        current = request.session.get(state.RECORD_ID)
        return Response(
            s.SessionSerializer(records, many=True, context={"current_record_id": current}).data
        )


class SessionRevokeView(CsrfProtectedView):
    permission_classes = [HasPermission("identity.session.revoke_own")]

    @extend_schema(tags=TAGS, summary="Revoke one of your sessions", responses={204: None})
    def delete(self, request: Request, session_id: str) -> Response:
        user = _user(request)
        record = get_or_404(sessions.active_sessions(user), session_id)
        if str(record.pk) == str(request.session.get(state.RECORD_ID)):
            sessions.end_session(request._request, reason="revoked_by_user")
        else:
            sessions.revoke_one(user, record, actor=user, request=request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RevokeOtherSessionsView(CsrfProtectedView):
    permission_classes = [HasPermission("identity.session.revoke_own")]

    @extend_schema(
        tags=TAGS,
        summary="Sign out all other sessions",
        request=None,
        responses=s.RevokedCountSerializer,
    )
    def post(self, request: Request) -> Response:
        user = _user(request)
        count = sessions.revoke_user_sessions(
            user,
            reason="revoked_by_user",
            keep=request._request,
            actor=user,
            request=request._request,
        )
        return Response({"revoked": count})


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise NotFound() from None
