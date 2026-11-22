"""Forms, the DynamicForm backend, workflows, notifications and the SLA sweep (Phase 5 M4)."""

from __future__ import annotations

import datetime as dt
import uuid
from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.utils import timezone

from apps.core.tenancy import tenant_atomic
from apps.customization import fields, forms, workflows
from apps.customization.models import WorkflowInstance, WorkflowStep
from apps.customization.tasks import sweep_workflow_sla
from apps.notifications_core.models import Notification
from apps.notifications_core.services import mark_read, notify, unread_count
from apps.tenancy.models import Membership
from tests.helpers import make_user
from tests.isolation.factories import grant_role, seed_tenant_roles, tenant_events

pytestmark = pytest.mark.django_db
ENTITY = "tenancy.member"
LAYOUT = {
    "sections": [
        {
            "key": "basic",
            "labels": {"en": "Basic"},
            "fields": [
                {"source": "core", "name": "display_name", "required": True},
                {"source": "custom", "name": "boarder"},
            ],
        },
        {
            "key": "hostel",
            "labels": {"en": "Hostel"},
            "visible_when": {"==": [{"var": "field.boarder"}, True]},
            "fields": [{"source": "custom", "name": "room_pref", "required": True}],
        },
    ]
}
SPEC = {
    "states": [
        {"key": "submitted", "labels": {"en": "Submitted"}},
        {"key": "approved", "labels": {"en": "Approved"}, "final": True},
        {"key": "rejected", "labels": {"en": "Rejected"}, "final": True},
    ],
    "initial": "submitted",
    "start_permission": "tenancy.member.view",
    "transitions": [
        {
            "key": "approve",
            "from": ["submitted"],
            "to": "approved",
            "labels": {"en": "Approve"},
            "permission": "tenancy.member.update",
            "guard": {">=": [{"var": "subject.age"}, 18]},
        },
        {
            "key": "reject",
            "from": ["submitted"],
            "to": "rejected",
            "labels": {"en": "Reject"},
            "permission": "tenancy.member.update",
        },
    ],
    "sla_hours": {"submitted": 24},
}


@pytest.fixture
def owner(org):
    user = make_user("studio-m4@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


def _fields(owner):
    fields.define_field(
        actor=owner, entity=ENTITY, key="boarder", field_type="boolean", labels={"en": "Boarder"}
    )
    fields.define_field(
        actor=owner,
        entity=ENTITY,
        key="room_pref",
        field_type="single_select",
        labels={"en": "Room preference"},
        options=[
            {"value": "single", "labels": {"en": "Single"}},
            {"value": "shared", "labels": {"en": "Shared"}},
        ],
    )


def test_forms_validate_layouts_and_submissions(org, owner):
    with tenant_atomic(org.tenant):
        _fields(owner)
        for bad, message in [
            ({"sections": []}, "1-20 sections"),
            (
                {"sections": [{"key": "sec", "fields": [{"source": "custom", "name": "nope"}]}]},
                "Unknown custom",
            ),
            (
                {"sections": [{"key": "sec", "fields": [{"source": "core", "name": "password"}]}]},
                "Unknown core",
            ),
            (
                {"sections": [{"key": "sec", "visible_when": {"eval": ["x"]}, "fields": []}]},
                "not allowed",
            ),
            (
                {
                    "sections": [
                        {"key": "sec", "fields": [{"source": "custom", "name": "boarder"}] * 2}
                    ]
                },
                "appears twice",
            ),
        ]:
            with pytest.raises(ValidationError, match=message):
                forms.save_form_draft(
                    actor=owner, key="join", entity=ENTITY, name="Join", layout=bad
                )
        forms.save_form_draft(actor=owner, key="join", entity=ENTITY, name="Join", layout=LAYOUT)
        with pytest.raises(ValidationError, match="unpublished"):
            forms.render("join")
        forms.publish_form(actor=owner, key="join")
        rendered = forms.render("join")
        assert [s["key"] for s in rendered["sections"]] == ["basic", "hostel"]
        room = rendered["sections"][1]["fields"][0]
        assert (room["type"], room["required"], len(room["options"])) == ("single_select", True, 2)
        assert rendered["sections"][1]["conditional"] is True

        assert forms.visible_sections("join", {"boarder": False}) == ["basic"]
        assert forms.visible_sections("join", {"boarder": True}) == ["basic", "hostel"]
        day = forms.validate_submission("join", {"display_name": "Ana", "boarder": False})
        assert day == {"core": {"display_name": "Ana"}, "custom": {"boarder": False}}
        with pytest.raises(ValidationError) as hidden:
            forms.validate_submission(
                "join", {"display_name": "Ana", "boarder": False, "room_pref": "single"}
            )
        assert hidden.value.message_dict == {"room_pref": ["This field is hidden."]}
        with pytest.raises(ValidationError) as missing:
            forms.validate_submission("join", {"display_name": "Ana", "boarder": True})
        assert missing.value.message_dict == {"room_pref": ["This field is required."]}
        with pytest.raises(ValidationError) as invalid:
            forms.validate_submission(
                "join", {"display_name": "", "boarder": True, "room_pref": "suite", "x": 1}
            )
        assert set(invalid.value.message_dict) == {"display_name", "room_pref", "x"}
    assert len(tenant_events(org.tenant, action="customization.form.published")) == 1


def test_workflow_specs_are_validated(org, owner):
    with tenant_atomic(org.tenant):
        broken = [
            ({**SPEC, "initial": "approved"}, "initial state"),
            ({**SPEC, "start_permission": "x.y.z"}, "start_permission"),
            (
                {**SPEC, "transitions": [{**SPEC["transitions"][0], "permission": "nope.a.b"}]},
                "unknown permission",
            ),
            (
                {**SPEC, "transitions": [{**SPEC["transitions"][0], "guard": {"var": "user.pw"}}]},
                "not available",
            ),
            ({**SPEC, "sla_hours": {"approved": 5}}, "sla_hours"),
            (
                {
                    **SPEC,
                    "transitions": [
                        {**SPEC["transitions"][1], "from": ["submitted"], "to": "submitted"}
                    ],
                },
                "No final state is reachable",
            ),
        ]
        for spec, message in broken:
            with pytest.raises(ValidationError, match=message):
                workflows.save_workflow_draft(
                    actor=owner, key="approval", subject=ENTITY, name="Approval", spec=spec
                )
        with pytest.raises(ValidationError, match="declared subjects"):
            workflows.save_workflow_draft(
                actor=owner, key="approval", subject="students.student", name="A", spec=SPEC
            )


def test_workflow_runs_with_permissions_guards_steps_and_notifications(
    org, owner, django_capture_on_commit_callbacks
):
    head = make_user("wf-head@example.com", mfa=True).user
    grant_role(org.tenant, head, "institution_admin", institution=org.north)
    teacher = make_user("wf-teacher@example.com").user
    grant_role(org.tenant, teacher, "teacher", institution=org.north, campus=org.main)
    subject = uuid.uuid4()
    with tenant_atomic(org.tenant):
        workflows.save_workflow_draft(
            actor=owner, key="approval", subject=ENTITY, name="Approval", spec=SPEC
        )
        workflows.publish_workflow(actor=owner, key="approval")
        instance = workflows.start(
            actor=owner, key="approval", subject_id=subject, context={"subject.age": 16, "x": 1}
        )
        assert instance.context == {"subject.age": 16}  # only subject.* values are kept
        assert instance.state == "submitted" and instance.sla_due_at is not None
        with pytest.raises(ValidationError, match="already has an open request"):
            workflows.start(actor=owner, key="approval", subject_id=subject)
        with pytest.raises(PermissionDenied):
            workflows.transition(actor=teacher, instance_id=instance.pk, transition_key="approve")
        with pytest.raises(ValidationError, match="conditions"):
            workflows.transition(actor=owner, instance_id=instance.pk, transition_key="approve")
        with pytest.raises(ValidationError, match="isn't available"):
            workflows.transition(actor=owner, instance_id=instance.pk, transition_key="nope")
        done = workflows.transition(
            actor=owner, instance_id=instance.pk, transition_key="reject", note="Too young"
        )
        assert (done.state, done.finished_at is not None, done.sla_due_at) == (
            "rejected",
            True,
            None,
        )
        with pytest.raises(ValidationError, match="finished"):
            workflows.transition(actor=owner, instance_id=instance.pk, transition_key="approve")
        [step] = WorkflowStep.objects.filter(instance=instance)
        assert (step.from_state, step.to_state, step.note) == ("submitted", "rejected", "Too young")
        # Approvers (holders of tenancy.member.update) and the starter were notified.
        owner_m = Membership.objects.get(user=owner)
        head_m = Membership.objects.get(user=head)
        teacher_m = Membership.objects.get(user=teacher)
        assert unread_count(owner_m.pk) >= 1 and unread_count(head_m.pk) >= 1
        assert unread_count(teacher_m.pk) == 0
        mine = list(Notification.objects.filter(membership=owner_m).values_list("pk", flat=True))
        assert mark_read(membership_id=owner_m.pk, notification_ids=mine) == len(mine)
        assert unread_count(owner_m.pk) == 0
        # A newer version doesn't change running instances (they pin theirs).
        adult = workflows.start(
            actor=owner, key="approval", subject_id=uuid.uuid4(), context={"subject.age": 30}
        )
        workflows.save_workflow_draft(
            actor=owner,
            key="approval",
            subject=ENTITY,
            name="Approval v2",
            spec={**SPEC, "transitions": [SPEC["transitions"][1]]},
        )
        workflows.publish_workflow(actor=owner, key="approval")
        approved = workflows.transition(actor=owner, instance_id=adult.pk, transition_key="approve")
        assert approved.state == "approved"
        with django_capture_on_commit_callbacks(execute=True):
            notify([owner_m.pk], kind="test", title="Hello", body="Body", link="/x", email=True)
        with pytest.raises(ValueError, match="relative"):
            notify([owner_m.pk], kind="test", title="x", link="https://evil.example")
    assert mail.outbox and mail.outbox[-1].subject == "Hello"
    actions = [
        e.action for e in tenant_events(org.tenant) if e.action.startswith("customization.workflow")
    ]
    assert actions.count("customization.workflow.transitioned") == 2


def test_sla_sweep_flags_overdue_requests(org, owner, tenant_site):
    with tenant_atomic(org.tenant):
        workflows.save_workflow_draft(
            actor=owner, key="approval", subject=ENTITY, name="Approval", spec=SPEC
        )
        workflows.publish_workflow(actor=owner, key="approval")
        instance = workflows.start(
            actor=owner, key="approval", subject_id=uuid.uuid4(), context={"subject.age": 20}
        )
        WorkflowInstance.objects.filter(pk=instance.pk).update(
            sla_due_at=timezone.now() - timedelta(minutes=1)
        )
    assert sweep_workflow_sla.delay().get() >= 1
    with tenant_atomic(org.tenant):
        instance.refresh_from_db()
        assert instance.sla_breached_at is not None
        assert Notification.objects.filter(title__startswith="Overdue").exists()
        assert workflows.mark_overdue() == 0  # flagged once


def test_definitions_instances_and_notifications_are_tenant_isolated(org, owner, tenant_site):
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(org.tenant):
        workflows.save_workflow_draft(
            actor=owner, key="approval", subject=ENTITY, name="Approval", spec=SPEC
        )
        workflows.publish_workflow(actor=owner, key="approval")
        workflows.start(actor=owner, key="approval", subject_id=uuid.uuid4(), context={})
    with tenant_atomic(other):
        with pytest.raises(ValidationError, match="unpublished"):
            workflows.start(actor=owner, key="approval", subject_id=uuid.uuid4())
        with connection.cursor() as cursor:  # raw SQL as erp_app: RLS, not the manager
            for table in (
                "customization_formdefinition",
                "customization_workflowdefinition",
                "customization_workflowinstance",
                "customization_workflowstep",
                "notifications_core_notification",
            ):
                cursor.execute(
                    f"SELECT count(*) FROM {table} WHERE tenant_id = %s", [org.tenant.id]
                )
                assert cursor.fetchone() == (0,), table


def test_guards_use_the_supplied_day_not_the_clock(org, owner):
    spec = {
        **SPEC,
        "transitions": [
            {
                **SPEC["transitions"][0],
                "guard": {"<=": [{"var": "subject.deadline"}, {"var": "today"}]},
            }
        ],
    }
    with tenant_atomic(org.tenant):
        workflows.save_workflow_draft(actor=owner, key="dated", subject=ENTITY, name="D", spec=spec)
        workflows.publish_workflow(actor=owner, key="dated")
        inst = workflows.start(
            actor=owner,
            key="dated",
            subject_id=uuid.uuid4(),
            context={"subject.deadline": "2026-06-01"},
        )
        with pytest.raises(ValidationError, match="conditions"):
            workflows.transition(
                actor=owner,
                instance_id=inst.pk,
                transition_key="approve",
                today=dt.date(2026, 5, 1),
            )
        assert (
            workflows.transition(
                actor=owner,
                instance_id=inst.pk,
                transition_key="approve",
                today=dt.date(2026, 6, 2),
            ).state
            == "approved"
        )
