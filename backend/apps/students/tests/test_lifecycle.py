"""Student lifecycle (Phase 7 M5; ADR-068, ADR-074 Q5): moving within a year, withdrawal,
transfer certificates, promotion with rule suggestions and staff confirmation, alumni,
printable documents from Studio templates, permissions, step-up and the API."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.academics import services as academics
from apps.core.tenancy import tenant_atomic
from apps.customization import fields, numbering, rule_services, template_services
from apps.module_registry import services as registry_services
from apps.students import lifecycle, services
from apps.students.models import Enrollment, Student, TransferCertificate
from apps.tenancy.models import Institution
from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1"
PASSED = {"==": [{"var": "student.passed"}, "yes"]}


@pytest.fixture
def owner(org):
    user = make_user("lifecycle-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


@pytest.fixture
def school(org, owner):
    """North: years 2027 and 2028; Six (sections 6A, 6B) and Seven (7A); Ana and Bo in 6A."""
    with tenant_atomic(org.tenant):
        Institution.objects.filter(pk=org.north.pk).update(
            preset_code="school.general.v2", preset_version="2"
        )
        years = [
            academics.create_year(
                actor=owner,
                institution=org.north,
                code=str(y),
                name=str(y),
                start_date=dt.date(y, 1, 1),
                end_date=dt.date(y, 12, 31),
            )
            for y in (2027, 2028)
        ]
        units = {}
        for cls, sections in (("6", ("6A", "6B")), ("7", ("7A",))):
            parent = academics.create_unit(
                actor=owner, institution=org.north, level_key="class", code=cls, name=cls
            )
            for code in sections:
                units[code] = academics.create_unit(
                    actor=owner, institution=org.north, level_key="section", code=code,
                    name=code, parent=parent,
                )  # fmt: skip
        fields.define_field(
            actor=owner, entity="students.student", key="passed", field_type="text",
            labels={"en": "Passed"},
        )  # fmt: skip
        people = {}
        for name, number, passed in (("Ana", "N-1", "yes"), ("Bo", "N-2", "no")):
            people[name] = services.create_student(
                actor=owner, institution=org.north, values={"name": name}, number=number,
                extra={"passed": passed},
            )  # fmt: skip
            services.enroll(
                actor=owner, student=people[name], year=years[0], unit=units["6A"],
                roll_number=number[-1], start_date=dt.date(2027, 1, 1),
            )  # fmt: skip
    return {"y27": years[0], "y28": years[1], **units, **people}


def test_moving_within_the_year_and_leaving(org, owner, school):
    with tenant_atomic(org.tenant):
        moved = lifecycle.move(actor=owner, student=school["Ana"], unit=school["6B"])
        assert (moved.unit_id, moved.year_id, moved.status) == (
            school["6B"].pk, school["y27"].pk, "active",
        )  # fmt: skip
        history = Enrollment.objects.filter(student=school["Ana"]).order_by("created_at")
        assert [e.status for e in history] == ["transferred", "active"]
        with pytest.raises(ValidationError, match="already in this unit"):
            lifecycle.move(actor=owner, student=school["Ana"], unit=school["6B"])
        with pytest.raises(ValidationError, match="Give a reason"):
            lifecycle.withdraw(actor=owner, student=school["Bo"], reason=" ")
        bo = lifecycle.withdraw(actor=owner, student=school["Bo"], reason="Moved abroad")
        assert bo.status == "withdrawn"
        assert not Enrollment.objects.filter(student=bo, status="active").exists()
        with pytest.raises(ValidationError, match="Only active students"):
            lifecycle.withdraw(actor=owner, student=bo, reason="Again")
        with pytest.raises(ValidationError, match="transfer_certificate"):
            lifecycle.issue_transfer_certificate(actor=owner, student=school["Ana"], reason="X")
        numbering.define_sequence(
            actor=owner, key="transfer_certificate", name="TC", pattern="TC-{SEQ:3}",
            scope="institution", reset="never",
        )  # fmt: skip
        tc = lifecycle.issue_transfer_certificate(
            actor=owner, student=school["Ana"], reason="Family moved", destination="City School"
        )
        assert tc.number == "TC-001"
        assert Student.objects.get(pk=school["Ana"].pk).status == "transferred"
        assert Enrollment.objects.filter(student=school["Ana"], status="transferred").count() == 2
    teacher = org.teacher
    with tenant_atomic(org.tenant), pytest.raises(PermissionDenied):
        lifecycle.withdraw(actor=teacher, student=school["Bo"], reason="X")


def test_promotion_suggests_from_the_rule_and_applies_staff_decisions(org, owner, school):
    frame = {"year_from": school["y27"], "unit_from": school["6A"], "year_to": school["y28"]}
    with tenant_atomic(org.tenant):
        rule_services.save_rule_draft(
            actor=owner, namespace_code="academics.promotion", key="passed", name="Passed",
            rule=PASSED,
            test_cases=[{"context": {"student.passed": "yes"}, "expected": True}],
        )  # fmt: skip
        rule_services.publish_rule(actor=owner, key="passed")
        rows = lifecycle.promotion_preview(
            actor=owner, unit_to=school["7A"], rule_key="passed", **frame
        )
        assert [(r["name"], r["suggestion"]) for r in rows] == [
            ("Ana", "promote"),
            ("Bo", "repeat"),
        ]
        final = lifecycle.promotion_preview(actor=owner, **frame)  # no next unit: final level
        assert {r["suggestion"] for r in final} == {"complete"}
        with pytest.raises(ValidationError, match="next academic year"):
            lifecycle.promotion_preview(
                actor=owner, year_from=school["y28"], unit_from=school["6A"],
                year_to=school["y27"], unit_to=school["7A"],
            )  # fmt: skip
        ana, bo = str(school["Ana"].pk), str(school["Bo"].pk)
        # One invalid decision rolls everything back.
        with pytest.raises(ValidationError):
            lifecycle.apply_promotion(
                actor=owner, unit_to=school["7A"], decisions={ana: "promote", bo: "fly"}, **frame
            )
        assert not Enrollment.objects.filter(year=school["y28"]).exists()
        # Staff overrule the suggestion for Bo (promote) and confirm Ana.
        counts = lifecycle.apply_promotion(
            actor=owner, unit_to=school["7A"], decisions={ana: "promote", bo: "repeat"}, **frame
        )
        assert counts == {"promote": 1, "repeat": 1, "complete": 0}
        next_units = dict(
            Enrollment.objects.filter(year=school["y28"]).values_list("student__name", "unit__code")
        )
        assert next_units == {"Ana": "7A", "Bo": "6A"}
        old = dict(
            Enrollment.objects.filter(year=school["y27"]).values_list("student__name", "status")
        )
        assert old == {"Ana": "promoted", "Bo": "repeated"}
        # Final level: completing makes the student alumni.
        done = lifecycle.apply_promotion(
            actor=owner, year_from=school["y28"], unit_from=school["7A"],
            year_to=academics.create_year(
                actor=owner, institution=org.north, code="2029", name="2029",
                start_date=dt.date(2029, 1, 1), end_date=dt.date(2029, 12, 31),
            ),
            decisions={ana: "complete"},
        )  # fmt: skip
        assert done["complete"] == 1
        assert Student.objects.get(pk=ana).status == "alumni"
    with tenant_atomic(org.tenant), pytest.raises(PermissionDenied):
        lifecycle.promotion_preview(actor=org.teacher, unit_to=school["7A"], **frame)


def test_documents_render_from_published_studio_templates(org, owner, school):
    card = {"en": {"body": "<p>{{ institution }} · {{ name }} ({{ number }}) {{ unit }}</p>"}}
    certificate = {
        "en": {"body": "<h1>{{ certificate_number }}</h1>{{ name }} → {{ destination }}"}
    }
    with tenant_atomic(org.tenant):
        Student.objects.filter(pk=school["Ana"].pk).update(name="Ana <b>")
        kinds = (
            ("card", "students.id_card", card),
            ("tc", "students.transfer_certificate", certificate),
        )
        for key, kind, content in kinds:
            template_services.save_template_draft(
                actor=owner, key=key, kind_code=kind, name=key, content=content
            )
            template_services.publish_template(actor=owner, key=key)
        ana = Student.objects.get(pk=school["Ana"].pk)
        html = lifecycle.id_card(actor=owner, student=ana, template_key="card")
        assert html == "<p>North · Ana &lt;b&gt; (N-1) 6A</p>"  # autoescaped
        with pytest.raises(ValidationError, match=r"students\.id_card"):
            lifecycle.id_card(actor=owner, student=ana, template_key="tc")  # wrong kind
        tc = lifecycle.issue_transfer_certificate(
            actor=owner, student=ana, reason="Moved", destination="City", number="T-9"
        )
        doc = lifecycle.transfer_certificate_document(
            actor=owner, certificate=tc, template_key="tc"
        )
        assert doc == "<h1>T-9</h1>Ana &lt;b&gt; → City"
        with pytest.raises(ValidationError, match="already used"):
            lifecycle.issue_transfer_certificate(
                actor=owner, student=school["Bo"], reason="Moved", number="T-9"
            )
    south = make_user("lc-south@example.com", mfa=True).user
    grant_role(org.tenant, south, "institution_admin", institution=org.south)
    with tenant_atomic(org.tenant), pytest.raises(PermissionDenied):
        lifecycle.id_card(actor=south, student=school["Bo"], template_key="card")


def test_the_lifecycle_api_with_step_up_for_promotion(org, owner, admin, school):
    for module in ("academics", "students"):
        registry_services.set_override(
            actor=admin.user, tenant_id=org.tenant.id, module_code=module, kind="grant",
            reason="Pilot agreement for students",
        )  # fmt: skip
    head = make_user("lc-head@example.com", mfa=True)
    grant_role(org.tenant, head.user, "institution_admin", institution=org.north)
    api = Api(host=tenant_host(org.tenant))
    api.login(head, expect="authenticated")
    ana, bo = school["Ana"].pk, school["Bo"].pk
    body = {"year_from": str(school["y27"].pk), "unit_from": str(school["6A"].pk),
            "year_to": str(school["y28"].pk), "unit_to": str(school["7A"].pk)}  # fmt: skip
    apply = {**body, "decisions": {str(ana): "promote", str(bo): "promote"}}
    no_step_up = api.post(f"{V1}/students/promotion/apply/", apply)
    assert no_step_up.status_code == 403  # promotion needs a fresh step-up
    api.step_up(head)
    preview = api.post(f"{V1}/students/promotion/preview/", body)
    assert [r["suggestion"] for r in preview.json()] == ["promote", "promote"]
    applied = api.post(f"{V1}/students/promotion/apply/", apply)
    assert applied.json() == {"promote": 2, "repeat": 0, "complete": 0}, applied.content
    moved = api.post(f"{V1}/students/{bo}/move/", {"unit": str(school["6B"].pk)})
    assert (moved.status_code, moved.json()["unit_name"]) == (201, "6B"), moved.content
    withdrawn = api.post(f"{V1}/students/{bo}/withdraw/", {"reason": "Moved abroad"})
    assert withdrawn.json()["status"] == "withdrawn"
    issued = api.post(
        f"{V1}/students/{ana}/transfer-certificates/", {"reason": "Moved", "number": "T-1"}
    )
    assert issued.status_code == 201, issued.content
    listed = api.get(f"{V1}/students/{ana}/transfer-certificates/").json()
    assert [c["number"] for c in listed] == ["T-1"]
    no_template = api.get(f"{V1}/students/{ana}/id-card/")
    assert no_template.status_code == 400
    missing = api.get(f"{V1}/students/{ana}/id-card/", template="nope")
    assert missing.status_code == 400
    teacher = Api(host=tenant_host(org.tenant))
    from tests.helpers import Person

    teacher.login(Person(user=org.teacher), expect="authenticated")
    assert teacher.post(f"{V1}/students/promotion/preview/", body).status_code == 403
    assert teacher.post(f"{V1}/students/{ana}/withdraw/", {"reason": "x"}).status_code == 403
    with tenant_atomic(org.tenant):
        assert TransferCertificate.objects.count() == 1
