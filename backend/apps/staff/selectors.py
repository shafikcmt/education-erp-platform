"""Who sees which staff profiles, and which units a member advises (Phase 7 M3; ADR-070, ADR-073).

* **scope:** ``staff.profile.view`` for the whole tenant or an institution covers every profile
  there; held for a campus, the profiles whose home campus it is.
* **own:** ``staff.profile.view_own`` (held in any scope) covers the profiles whose login is the
  member.

Everything else is invisible, and views answer 404 for it.

:func:`advised_units` is a ``STUDENTS_ASSIGNED_UNITS`` source: class teachers see the students
of the units they advise, in years that are not closed.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.core.tenancy import require_tenant
from apps.rbac.engine import has_perm
from apps.staff.models import StaffProfile, UnitAdvisor

VIEW, OWN = "staff.profile.view", "staff.profile.view_own"


def memberships(actor: Any) -> list[Any]:
    from apps.tenancy.models import Membership

    return list(
        Membership.objects.filter(user_id=actor.pk, status=Membership.Status.ACTIVE).values_list(
            "pk", flat=True
        )
    )


def _scope_filter(actor: Any) -> tuple[Q | None, bool]:
    """``staff.profile.view`` grounds (``None`` means the whole tenant) and whether the member
    holds ``staff.profile.view_own`` anywhere."""
    from apps.tenancy.api.permissions import actor_targets

    institutions, campuses, own = set(), set(), False
    for target in actor_targets(actor, require_tenant().id):
        own = own or has_perm(actor, OWN, target=target, use_cache=False)
        if not has_perm(actor, VIEW, target=target, use_cache=False):
            continue
        if target.institution_id is None:
            return None, own
        if target.campus_id is None:
            institutions.add(target.institution_id)
        else:
            campuses.add(target.campus_id)
    return Q(institution_id__in=institutions) | Q(campus_id__in=campuses), own


def visible_profiles(actor: Any) -> QuerySet[StaffProfile]:
    if not getattr(actor, "is_authenticated", False):
        return StaffProfile.objects.none()
    scope, own = _scope_filter(actor)
    if scope is None:
        return StaffProfile.objects.all()
    if own:
        mine = memberships(actor)
        if mine:
            scope |= Q(membership_id__in=mine)
    return StaffProfile.objects.filter(scope)


def visible_profile(actor: Any, profile_id: Any) -> StaffProfile | None:
    import uuid

    try:
        uuid.UUID(str(profile_id))
    except ValueError:
        return None
    return visible_profiles(actor).filter(pk=profile_id).first()


def advised_units(actor: Any, memberships: list[Any]) -> dict[Any, set[Any]]:
    """Units the member advises (as an active staff member) in years that are not closed, per
    institution."""
    from apps.academics.models import AcademicYear

    rows = (
        UnitAdvisor.objects.filter(
            staff__membership_id__in=memberships, staff__status=StaffProfile.Status.ACTIVE
        )
        .exclude(year__status=AcademicYear.Status.CLOSED)
        .values_list("institution_id", "unit_id")
    )
    units: dict[Any, set[Any]] = {}
    for institution_id, unit_id in rows:
        units.setdefault(institution_id, set()).add(unit_id)
    return units


def advisor_memberships(year_id: Any, unit_ids: set[Any]) -> dict[Any, list[Any]]:
    """Logins of the active class teachers of each unit in the year (Phase 8 M5 notices)."""
    rows = UnitAdvisor.objects.filter(
        year_id=year_id,
        unit_id__in=unit_ids,
        staff__status=StaffProfile.Status.ACTIVE,
        staff__membership_id__isnull=False,
    ).values_list("unit_id", "staff__membership_id")
    out: dict[Any, list[Any]] = {}
    for unit, membership in rows:
        out.setdefault(unit, []).append(membership)
    return out
