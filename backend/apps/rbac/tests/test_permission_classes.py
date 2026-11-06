"""DRF permission classes: HasPermission method mapping and HasAnyPermission."""

import pytest
from django.test import RequestFactory
from rest_framework.exceptions import NotAuthenticated
from rest_framework.request import Request

from apps.identity import session_state as state
from apps.rbac.engine import PLATFORM
from apps.rbac.permissions import HasAnyPermission, HasPermission
from tests.helpers import make_user

pytestmark = pytest.mark.django_db


class _View:
    allow_during_mfa_enrollment = False


def _request(user, method="get", *, mfa=True):
    django_request = getattr(RequestFactory(), method)("/")
    django_request.session = {state.MFA_VERIFIED_AT: state.now_ts()} if mfa else {}
    django_request.scope_target = PLATFORM
    django_request.user = user
    request = Request(django_request)
    request.user = user
    return request


def test_method_mapping_denies_unmapped_methods():
    check = HasPermission({"GET": "identity.account.view_own"})()
    user = make_user().user
    assert check.has_permission(_request(user), _View())
    assert not check.has_permission(_request(user, "post"), _View())


def test_has_any_permission():
    support = make_user("s@example.com", roles=("platform_support",), mfa=True).user
    plain = make_user("p@example.com").user
    check = HasAnyPermission("rbac.role.view", "identity.user.view")()
    assert check.has_permission(_request(support), _View())
    assert not check.has_permission(_request(plain), _View())
    with pytest.raises(NotAuthenticated):
        from django.contrib.auth.models import AnonymousUser

        check.has_permission(_request(AnonymousUser()), _View())
    with pytest.raises(ValueError, match="at least one"):
        HasAnyPermission()


def test_has_any_permission_still_requires_an_mfa_session():
    from apps.identity.errors import MfaRequired

    support = make_user("s@example.com", roles=("platform_support",), mfa=True).user
    check = HasAnyPermission("identity.user.view")()
    with pytest.raises(MfaRequired):
        check.has_permission(_request(support, mfa=False), _View())
