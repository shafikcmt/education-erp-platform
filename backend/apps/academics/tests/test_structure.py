"""Academic structure (Phase 6 M1; ADR-063): one model for every institution type, driven by
presets and capability flags; scoped permissions; composite tenant keys and RLS."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.utils import IntegrityError

from apps.academics import capabilities as caps
from apps.academics import services
from apps.academics.models import Unit
from apps.core.tenancy import tenant_atomic
from apps.customization import services as config
from apps.customization.scopes import ConfigScope
from apps.tenancy.models import Institution, Membership
from tests.helpers import make_user
from tests.isolation.factories import grant_role, seed_tenant_roles

pytestmark = pytest.mark.django_db

# Expected organisational levels and flags of the v2 presets (ADR-063).
PRESETS = {
    "school": ("school.general.v2", ["class", "section"], False, False),
    "college": ("college.general.v2", ["group", "class", "section"], False, False),
    "university": ("university.credit.v2", ["faculty", "department", "program"], True, True),
    "madrasa": ("madrasa.general.v2", ["marhala", "jamaat"], False, False),
    "coaching_center": ("coaching.general.v2", ["program", "batch"], False, False),
    "training_institute": ("training.general.v2", ["program", "batch"], False, False),
}


@pytest.fixture
def owner(org):
    user = make_user("academics-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


def _institution(org, itype, code=None, preset=None):
    with tenant_atomic(org.tenant):
        return Institution.objects.create(
            code=code or itype.replace("_", "-")[:30],
            name=itype,
            institution_type=itype,
            preset_code=preset or PRESETS[itype][0],
            preset_version="2",
        )


def _year(owner, inst, code="2027", start=(2027, 1, 1), end=(2027, 12, 31)):
    return services.create_year(
        actor=owner,
        institution=inst,
        code=code,
        name=code,
        start_date=dt.date(*start),
        end_date=dt.date(*end),
    )


# --------------------------------------------------------------------------- presets
@pytest.mark.parametrize("itype", sorted(PRESETS))
def test_every_institution_type_builds_its_tree_from_configuration(org, owner, itype):
    """The same code paths build every type's structure: only the configuration differs."""
    _, levels, credit, semester = PRESETS[itype]
    inst = _institution(org, itype)
    with tenant_atomic(org.tenant):
        assert caps.unit_levels(inst.pk) == levels
        assert caps.capability(inst.pk, caps.CREDIT_BASED) is credit
        assert caps.capability(inst.pk, caps.SEMESTER_BASED) is semester
        parent = None
        for depth, level in enumerate(levels):
            parent = services.create_unit(
                actor=owner,
                institution=inst,
                level_key=level,
                code=f"u{depth}",
                name=level,
                parent=parent,
            )
        # A lower level without its parent, or an unknown level: refused.
        with pytest.raises(ValidationError, match="one level below"):
            services.create_unit(
                actor=owner, institution=inst, level_key=levels[-1], code="x", name="x"
            )
        with pytest.raises(ValidationError):
            services.create_unit(
                actor=owner, institution=inst, level_key="nope", code="y", name="y"
            )
        assert Unit.objects.filter(institution=inst).count() == len(levels)


def test_v1_institutions_ignore_time_and_subject_levels(org, owner):
    inst = _institution(org, "school", code="old", preset="school.general.v1")
    with tenant_atomic(org.tenant):
        assert caps.unit_levels(inst.pk) == ["class", "section"]  # v1 also lists year/subject


# --------------------------------------------------------------------------- years and terms
def test_years_do_not_overlap_one_is_active_and_closed_years_are_locked(org, owner):
    inst = _institution(org, "school")
    with tenant_atomic(org.tenant):
        y27 = _year(owner, inst)
        with pytest.raises(ValidationError, match="overlap"):
            _year(owner, inst, code="x", start=(2027, 6, 1), end=(2028, 5, 31))
        y28 = _year(owner, inst, code="2028", start=(2028, 1, 1), end=(2028, 12, 31))
        services.set_year_status(actor=owner, year=y27, status="active")
        with pytest.raises(ValidationError, match="active year"):
            services.set_year_status(actor=owner, year=y28, status="active")
        services.set_year_status(actor=owner, year=y27, status="closed")
        with pytest.raises(ValidationError):
            services.set_year_status(actor=owner, year=y27, status="active")
        with pytest.raises(ValidationError, match="closed"):
            services.create_term(
                actor=owner,
                year=y27,
                code="t1",
                name="T1",
                start_date=dt.date(2027, 1, 1),
                end_date=dt.date(2027, 4, 30),
            )
        services.create_term(
            actor=owner,
            year=y28,
            code="t1",
            name="T1",
            start_date=dt.date(2028, 1, 1),
            end_date=dt.date(2028, 4, 30),
        )
        for start, end in (((2028, 4, 1), (2028, 6, 30)), ((2027, 12, 1), (2028, 2, 1))):
            with pytest.raises(ValidationError):  # overlapping, outside the year
                services.create_term(
                    actor=owner,
                    year=y28,
                    code="t2",
                    name="T2",
                    start_date=dt.date(*start),
                    end_date=dt.date(*end),
                )


# --------------------------------------------------------------------------- capability flags
def test_credits_follow_the_credit_based_flag(org, owner):
    uni, school = _institution(org, "university"), _institution(org, "school")
    with tenant_atomic(org.tenant):
        with pytest.raises(ValidationError, match="required"):
            services.create_subject(actor=owner, institution=uni, code="cse101", name="Intro")
        services.create_subject(
            actor=owner, institution=uni, code="cse101", name="Intro", credits=Decimal("3.00")
        )
        with pytest.raises(ValidationError, match="does not use credits"):
            services.create_subject(
                actor=owner, institution=school, code="math", name="Maths", credits=Decimal("1")
            )
        services.create_subject(actor=owner, institution=school, code="math", name="Maths")


def test_offerings_need_a_term_when_semester_based_and_check_their_parts(org, owner):
    uni, school = _institution(org, "university"), _institution(org, "school")
    with tenant_atomic(org.tenant):
        year = _year(owner, uni)
        other_year = _year(owner, uni, code="2028", start=(2028, 1, 1), end=(2028, 12, 31))
        term = services.create_term(
            actor=owner,
            year=year,
            kind="semester",
            code="s1",
            name="Spring",
            start_date=dt.date(2027, 1, 1),
            end_date=dt.date(2027, 6, 30),
        )
        fac = services.create_unit(
            actor=owner, institution=uni, level_key="faculty", code="eng", name="Eng"
        )
        course = services.create_subject(
            actor=owner, institution=uni, code="cse101", name="Intro", credits=Decimal("3")
        )
        with pytest.raises(ValidationError, match="term is required"):
            services.create_offering(actor=owner, year=year, unit=fac, subject=course)
        with pytest.raises(ValidationError, match="another year"):
            services.create_offering(
                actor=owner, year=other_year, unit=fac, subject=course, term=term
            )
        offering = services.create_offering(
            actor=owner, year=year, unit=fac, subject=course, term=term
        )
        with pytest.raises(ValidationError, match="already offered"):
            services.create_offering(actor=owner, year=year, unit=fac, subject=course, term=term)
        # A subject of another institution can't be offered here.
        maths = services.create_subject(actor=owner, institution=school, code="m", name="M")
        with pytest.raises(ValidationError, match="one institution"):
            services.create_offering(actor=owner, year=year, unit=fac, subject=maths, term=term)
        # Teachers are active members; the unit can't be archived while it has offerings.
        teacher = Membership.objects.get(user=org.teacher)
        services.assign_teacher(actor=owner, offering=offering, membership=teacher)
        with pytest.raises(ValidationError, match="Already"):
            services.assign_teacher(actor=owner, offering=offering, membership=teacher)
        with pytest.raises(ValidationError, match="offerings"):
            services.archive_unit(actor=owner, unit=fac)


# --------------------------------------------------------------------------- permissions
def test_permissions_are_checked_in_the_institution_scope(org):
    head = make_user("head-mfa@example.com", mfa=True).user
    grant_role(org.tenant, head, "institution_admin", institution=org.north)
    with tenant_atomic(org.tenant):
        for inst in (org.north, org.south):
            Institution.objects.filter(pk=inst.pk).update(
                preset_code=PRESETS[inst.institution_type][0], preset_version="2"
            )
        services.create_unit(
            actor=head, institution=org.north, level_key="class", code="c1", name="One"
        )
        with pytest.raises(PermissionDenied):  # another institution
            services.create_unit(
                actor=head, institution=org.south, level_key="marhala", code="m1", name="M"
            )
        with pytest.raises(PermissionDenied):  # teachers read the structure only
            services.create_unit(
                actor=org.teacher, institution=org.north, level_key="class", code="c2", name="T"
            )


# --------------------------------------------------------------------------- isolation
def test_units_are_invisible_and_unreachable_from_another_tenant(org, owner, tenant_site):
    inst = _institution(org, "school")
    with tenant_atomic(org.tenant):
        unit = services.create_unit(
            actor=owner, institution=inst, level_key="class", code="c1", name="One"
        )
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(other):
        assert not Unit.objects.exists()
        with connection.cursor() as cursor:  # raw SQL as erp_app: RLS, not the manager
            cursor.execute("SELECT count(*) FROM academics_unit WHERE id = %s", [unit.pk])
            assert cursor.fetchone() == (0,)
        # A row of this tenant can't point at the other tenant's institution (composite key).
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO academics_unit (id, tenant_id, institution_id, level_key, code, "
                'name, name_i18n, "order", created_at, updated_at) VALUES '
                "(gen_random_uuid(), %s, %s, 'class', 'x', 'x', '{}', 0, now(), now())",
                [other.id, inst.pk],
            )


# --------------------------------------------------------------------------- publish check
def test_publishing_levels_that_strand_units_is_refused(org, owner):
    inst = _institution(org, "school")
    scope = ConfigScope(inst.pk)
    with tenant_atomic(org.tenant):
        services.create_unit(
            actor=owner, institution=inst, level_key="class", code="c1", name="One"
        )
        config.save_draft(
            actor=owner, scope=scope, data={"customization.structure_levels": [{"key": "grade"}]}
        )
    with pytest.raises(ValidationError, match="used by units"), tenant_atomic(org.tenant):
        config.publish(actor=owner, scope=scope)
    with tenant_atomic(org.tenant):  # the refused publish left nothing behind
        assert caps.unit_levels(inst.pk) == ["class", "section"]
        # Adding a level below the existing ones is fine.
        config.save_draft(
            actor=owner,
            scope=scope,
            data={
                "customization.structure_levels": [
                    {"key": "class"},
                    {"key": "section"},
                    {"key": "group"},
                ]
            },
        )
        config.publish(actor=owner, scope=scope)
        assert caps.unit_levels(inst.pk) == ["class", "section", "group"]
