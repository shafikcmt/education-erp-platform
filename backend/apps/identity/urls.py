"""identity routes, mounted under /api/v1/ (plan §8)."""

from django.urls import path

from apps.identity.api import views_auth as a
from apps.identity.api import views_me as m
from apps.identity.api import views_platform as p

app_name = "identity"

urlpatterns = [
    # anonymous / session-only (reviewed allow-list in the URL authorization audit)
    path("auth/csrf/", a.CsrfView.as_view(), name="auth-csrf"),
    path("auth/login/", a.LoginView.as_view(), name="auth-login"),
    path("auth/mfa/verify/", a.MfaVerifyView.as_view(), name="auth-mfa-verify"),
    path("auth/logout/", a.LogoutView.as_view(), name="auth-logout"),
    path("auth/step-up/", a.StepUpView.as_view(), name="auth-step-up"),
    path("auth/password/reset/", a.PasswordResetView.as_view(), name="auth-password-reset"),
    path(
        "auth/password/reset/confirm/",
        a.PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path("auth/activate/", a.ActivateView.as_view(), name="auth-activate"),
    path(
        "auth/activation/resend/", a.ActivationResendView.as_view(), name="auth-activation-resend"
    ),
    path("auth/email/verify/", a.EmailVerifyView.as_view(), name="auth-email-verify"),
    # self-service
    path("me/", m.MeView.as_view(), name="me"),
    path("me/password/", m.PasswordChangeView.as_view(), name="me-password"),
    path("me/email/", m.EmailChangeView.as_view(), name="me-email"),
    path("me/mfa/", m.MfaStatusView.as_view(), name="me-mfa"),
    path("me/mfa/totp/", m.MfaDisableView.as_view(), name="me-mfa-totp"),
    path("me/mfa/totp/setup/", m.MfaSetupView.as_view(), name="me-mfa-setup"),
    path(
        "me/mfa/totp/setup/<str:device_id>/",
        m.MfaSetupCancelView.as_view(),
        name="me-mfa-setup-cancel",
    ),
    path(
        "me/mfa/totp/setup/<str:device_id>/manual-key/",
        m.MfaManualKeyView.as_view(),
        name="me-mfa-manual-key",
    ),
    path("me/mfa/totp/confirm/", m.MfaConfirmView.as_view(), name="me-mfa-confirm"),
    path("me/mfa/recovery-codes/", m.RecoveryCodesView.as_view(), name="me-mfa-recovery-codes"),
    path("me/sessions/", m.SessionsView.as_view(), name="me-sessions"),
    path(
        "me/sessions/revoke-others/",
        m.RevokeOtherSessionsView.as_view(),
        name="me-sessions-revoke-others",
    ),
    path("me/sessions/<str:session_id>/", m.SessionRevokeView.as_view(), name="me-session"),
    # platform user administration
    path("platform/users/", p.PlatformUsersView.as_view(), name="platform-users"),
    path("platform/users/<str:user_id>/", p.PlatformUserDetailView.as_view(), name="platform-user"),
    path(
        "platform/users/<str:user_id>/deactivate/",
        p.DeactivateUserView.as_view(),
        name="platform-user-deactivate",
    ),
    path(
        "platform/users/<str:user_id>/reactivate/",
        p.ReactivateUserView.as_view(),
        name="platform-user-reactivate",
    ),
    path(
        "platform/users/<str:user_id>/sessions/revoke/",
        p.RevokeUserSessionsView.as_view(),
        name="platform-user-sessions-revoke",
    ),
    path(
        "platform/users/<str:user_id>/mfa/reset/",
        p.ResetUserMfaView.as_view(),
        name="platform-user-mfa-reset",
    ),
    path(
        "platform/users/<str:user_id>/activation/resend/",
        p.ResendActivationView.as_view(),
        name="platform-user-activation-resend",
    ),
]
