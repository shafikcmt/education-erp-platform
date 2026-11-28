"""Attendance data model (Phase 8 M1; ADR-076, ADR-080): the database keeps registers unique and
records inside their register's institution and date; settings resolve from the v3 presets;
the permission catalogue; tenant isolation."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction

from apps.academics import services as academics
from apps.attendance.config import config_for
from apps.attendance.models import LeaveRequest, Record, Register, StaffRecord, Status
from apps.core.tenancy import tenant_atomic
from apps.rbac.registry import declared_permissions
from apps.staff import services as staff
from apps.students import services as students
from apps.tenancy.models import Institution
from tests.helpers import make_user
from tests.isolation.factories import grant_role, seed_tenant_roles

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
DAY = dt.date(2027, 3, 1)


@pytest.fixture
def owner(org):
    user = make_user("att-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


@pytest.fixture
def school(org, owner):
    """North (school v3): 2027, class Six with section A, a Maths offering in A, student Ana
    enrolled in A, staff member Rahim. South: student Sam."""
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="school.general.v3", preset_version="3"
        )
        year = academics.create_year(
            actor=owner, institution=org.north, code="2027", name="2027",
            start_date=dt.date(2027, 1, 1), end_date=dt.date(2027, 12, 31),
        )  # fmt: skip
        six = academics.create_unit(
            actor=owner, institution=org.north, level_key="class", code="6", name="Six",
            campus=org.main,
        )  # fmt: skip
        a = academics.create_unit(
            actor=owner, institution=org.north, level_key="section", code="6A", name="A",
            parent=six, campus=org.main,
        )  # fmt: skip
        maths = academics.create_subject(actor=owner, institution=org.north, code="M", name="M")
        offering = academics.create_offering(actor=owner, year=year, unit=a, subject=maths)
        ana = students.create_student(
            actor=owner, institution=org.north, values={"name": "Ana"}, number="N-1"
        )
        students.enroll(actor=owner, student=ana, year=year, unit=a)
        sam = students.create_student(
            actor=owner, institution=org.south, values={"name": "Sam"}, number="S-1"
        )
        rahim = staff.create_profile(
            actor=owner, institution=org.north, values={"name": "Rahim"}, number="T-1"
        )
    return {"year": year, "a": a, "offering": offering, "ana": ana, "sam": sam, "rahim": rahim}


def _register(org, w, **kw):
    fields = {
        "institution_id": org.north.pk, "campus_id": org.main.pk, "year": w["year"],
        "unit": w["a"], "date": DAY, "kind": Register.Kind.DAILY,
    }  # fmt: skip
    fields.update(kw)
    return Register.objects.create(**fields)


def test_one_daily_register_per_unit_and_date_and_one_period_register_per_lecture(org, school):
    w = school
    with tenant_atomic(org.tenant):
        _register(org, w)
        with pytest.raises(IntegrityError), transaction.atomic():
            _register(org, w)
        period = {"kind": Register.Kind.PERIOD, "offering": w["offering"]}
        _register(org, w, **period)
        _register(org, w, sequence=2, **period)  # a second lecture the same day
        with pytest.raises(IntegrityError), transaction.atomic():
            _register(org, w, **period)
        with pytest.raises(IntegrityError), transaction.atomic():
            _register(org, w, kind=Register.Kind.PERIOD, date=DAY + dt.timedelta(1))  # no offering
        with pytest.raises(IntegrityError), transaction.atomic():
            _register(org, w, date=DAY + dt.timedelta(2), offering=w["offering"])  # daily, offering


def test_records_stay_inside_their_register(org, school):
    """The date and institution copied onto a record must be the register's (composite key on
    ``(register, date)``); the student must belong to the register's institution."""
    w = school
    with tenant_atomic(org.tenant):
        reg = _register(org, w)
        Record.objects.create(
            institution_id=org.north.pk, register=reg, student=w["ana"], date=DAY,
            status=Status.ABSENT,
        )  # fmt: skip
        with pytest.raises(IntegrityError), transaction.atomic():  # the same student twice
            Record.objects.create(
                institution_id=org.north.pk, register=reg, student=w["ana"], date=DAY,
                status=Status.PRESENT,
            )  # fmt: skip
        with pytest.raises(IntegrityError), transaction.atomic():  # a different date
            Record.objects.create(
                institution_id=org.north.pk, register=_register(org, w, date=DAY + dt.timedelta(1)),
                student=w["ana"], date=DAY, status=Status.PRESENT,
            )  # fmt: skip
        with pytest.raises(IntegrityError), transaction.atomic():  # a South student
            Record.objects.create(
                institution_id=org.north.pk, register=reg, student=w["sam"], date=DAY,
                status=Status.PRESENT,
            )  # fmt: skip
        with pytest.raises(IntegrityError), transaction.atomic():  # an unknown status
            Record.objects.filter(register=reg).update(status="sleeping")
        with pytest.raises(IntegrityError), transaction.atomic():  # minutes only when late
            Record.objects.filter(register=reg).update(late_minutes=5)


def test_staff_records_and_leave_requests_are_checked(org, school):
    w = school
    with tenant_atomic(org.tenant):
        StaffRecord.objects.create(
            institution_id=org.north.pk, staff=w["rahim"], date=DAY, status=Status.PRESENT,
            check_in=dt.time(8, 0), check_out=dt.time(14, 0),
        )  # fmt: skip
        with pytest.raises(IntegrityError), transaction.atomic():  # one per day
            StaffRecord.objects.create(
                institution_id=org.north.pk, staff=w["rahim"], date=DAY, status=Status.ABSENT
            )
        with pytest.raises(IntegrityError), transaction.atomic():  # out before in
            StaffRecord.objects.create(
                institution_id=org.north.pk, staff=w["rahim"], date=DAY + dt.timedelta(1),
                status=Status.PRESENT, check_in=dt.time(9, 0), check_out=dt.time(8, 0),
            )  # fmt: skip
        with pytest.raises(IntegrityError), transaction.atomic():  # a South campus
            StaffRecord.objects.create(
                institution_id=org.north.pk, campus_id=org.south_main.pk, staff=w["rahim"],
                date=DAY + dt.timedelta(2), status=Status.PRESENT,
            )  # fmt: skip
        base = {"institution_id": org.north.pk, "start_date": DAY, "end_date": DAY, "reason": "x"}
        LeaveRequest.objects.create(student=w["ana"], **base)
        LeaveRequest.objects.create(staff=w["rahim"], **base)
        bad = [
            {"student": w["ana"], "staff": w["rahim"]},  # two people
            {},  # nobody
            {"student": w["ana"], "end_date": DAY - dt.timedelta(1)},  # ends before it starts
            {"student": w["ana"], "end_date": DAY + dt.timedelta(1), "half_day": True},
            {"student": w["sam"]},  # a South student in North
        ]
        for change in bad:
            with pytest.raises(IntegrityError), transaction.atomic():
                LeaveRequest.objects.create(**{**base, **change})


def test_settings_come_from_the_v3_presets_and_core_defaults(org, school):
    with tenant_atomic(org.tenant):
        north = config_for(org.north.pk, org.main.pk)
        assert (north.mode, north.takes_daily, north.takes_period) == ("daily", True, False)
        assert (north.edit_window_days, north.lock_after_days, north.threshold_percent) == (
            3, 30, 75,
        )  # fmt: skip
        assert north.default_status == "present"
        assert (north.alert_guardians, north.alert_email) == (True, False)
        for code, mode in (
            ("university.credit.v3", "period"),
            ("coaching.general.v3", "period"),
            ("madrasa.general.v3", "daily"),
            ("school.general.v2", "daily"),
        ):
            Institution.objects.filter(pk=org.south.pk).update(
                preset_code=code, preset_version=code[-1]
            )
            cache.clear()  # resolved configuration is cached; a real preset change publishes
            assert config_for(org.south.pk).mode == mode, code  # v2 falls back to the core default


def test_the_catalogue_declares_eight_codes_with_mfa_on_the_powerful_ones():
    codes = {c: p for c, p in declared_permissions().items() if c.startswith("attendance.")}
    assert len(codes) == 8
    mfa = {c for c, p in codes.items() if p.requires_mfa}
    assert mfa == {"attendance.record.manage", "attendance.staff.mark"}


def test_attendance_is_invisible_to_another_tenant(org, school, tenant_site):
    w = school
    with tenant_atomic(org.tenant):
        reg = _register(org, w)
        Record.objects.create(
            institution_id=org.north.pk, register=reg, student=w["ana"], date=DAY,
            status=Status.PRESENT,
        )  # fmt: skip
        StaffRecord.objects.create(
            institution_id=org.north.pk, staff=w["rahim"], date=DAY, status=Status.PRESENT
        )
        LeaveRequest.objects.create(
            institution_id=org.north.pk, student=w["ana"], start_date=DAY, end_date=DAY,
            reason="x",
        )  # fmt: skip
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(other):
        assert not Register.objects.exists() and not Record.objects.exists()
        with connection.cursor() as cursor:
            for table in ("attendance_register", "attendance_record", "attendance_staffrecord",
                          "attendance_leaverequest"):  # fmt: skip
                cursor.execute(f"SELECT count(*) FROM {table}")
                assert cursor.fetchone() == (0,)
