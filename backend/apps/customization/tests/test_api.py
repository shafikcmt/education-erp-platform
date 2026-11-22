"""Customization Studio API (Phase 5 M6; plan §9): allowed and denied, step-up on publish,
scopes, quotas, custom field values with masking, notifications and presets."""

from __future__ import annotations

import uuid

import pytest

from tests.helpers import Api, make_user
from tests.isolation.factories import grant_role, tenant_host

pytestmark = pytest.mark.django_db(databases=["default", "audit_durable"])
V1 = "/api/v1/customization"


def _member(org, email, template, *, step_up=True, **scope):
    person = make_user(email, mfa=template != "teacher")
    grant_role(org.tenant, person.user, template, **scope)
    api = Api(host=tenant_host(org.tenant))
    api.login(person, expect="authenticated")
    if step_up and template != "teacher":
        api.step_up(person)
    return api


def test_members_without_studio_permissions_are_refused(org):
    teacher = _member(org, "t@example.com", "teacher", institution=org.north, campus=org.main)
    for path in (
        "catalog/",
        "config/",
        "fields/",
        "rules/",
        "forms/",
        "workflows/",
        "templates/",
        "numbering/",
    ):
        response = teacher.get(f"{V1}/{path}")
        assert response.status_code == 403, (path, response.content)
    assert (
        teacher.post(
            f"{V1}/rules/test/", {"namespace": "x", "rule": 1, "test_cases": []}
        ).status_code
        == 403
    )


def test_configuration_draft_publish_rollback_and_scopes(org):
    owner = _member(org, "o@example.com", "tenant_owner")
    catalog = owner.get(f"{V1}/catalog/").json()
    assert "tenancy.week_start" in catalog["settings"] and "tenancy.member" in catalog["entities"]
    saved = owner.send(
        "put", f"{V1}/config/", {"data": {"tenancy.week_start": 6}, "note": "Saturday"}
    )
    assert saved.status_code == 200, saved.content
    assert saved.json()["draft"]["data"] == {"tenancy.week_start": 6}
    bad = owner.send("put", f"{V1}/config/", {"data": {"tenancy.week_start": 9}})
    assert bad.status_code == 400
    published = owner.post(f"{V1}/config/publish/", {"note": "go"})
    assert published.status_code == 200, published.content
    assert published.json()["effective"]["tenancy.week_start"] == 6
    owner.send("put", f"{V1}/config/", {"data": {"tenancy.week_start": 7}})
    owner.post(f"{V1}/config/publish/", {})
    rolled = owner.post(f"{V1}/config/rollback/", {"number": 1})
    assert rolled.json()["effective"]["tenancy.week_start"] == 6
    assert [v["number"] for v in rolled.json()["history"]] == [3, 2, 1]
    # Publishing needs a fresh step-up (permission flag).
    stale = _member(org, "o2@example.com", "tenant_owner", step_up=False)
    stale.send("put", f"{V1}/config/", {"data": {"tenancy.week_start": 2}})
    assert stale.post(f"{V1}/config/publish/", {}).json()["code"] == "step_up_required"
    # An institution admin sees and edits only their institution's scope.
    head = _member(org, "h@example.com", "institution_admin", institution=org.north)
    mine = head.get(f"{V1}/config/", institution=str(org.north.pk))
    assert mine.status_code == 200 and mine.json()["scope"] == "institution"
    assert head.get(f"{V1}/config/", institution=str(org.south.pk)).status_code == 404
    assert head.get(f"{V1}/config/").status_code == 404  # the whole organisation: not theirs
    denied = head.send("put", f"{V1}/config/", {"data": {}, "institution": str(org.south.pk)})
    assert denied.status_code == 403


def test_fields_quota_and_custom_values_with_masking(org, settings):
    owner = _member(org, "o@example.com", "tenant_owner")
    body = {
        "entity": "tenancy.institution",
        "key": "founded",
        "field_type": "number",
        "labels": {"en": "Founded"},
    }
    assert owner.post(f"{V1}/fields/", body).status_code == 201
    secret = {
        "entity": "tenancy.institution",
        "key": "bank_ref",
        "field_type": "text",
        "labels": {"en": "Bank ref"},
        "view_permission": "audit.event.view_ip",
    }
    created = owner.post(f"{V1}/fields/", secret).json()
    patched = owner.patch(f"{V1}/fields/{created['id']}/", {"labels": {"en": "Bank reference"}})
    assert patched.json()["labels"] == {"en": "Bank reference"}
    # Unknown attributes (e.g. the type) are ignored by the update serializer: nothing changes.
    same = owner.patch(f"{V1}/fields/{created['id']}/", {"field_type": "number"}).json()
    assert same["field_type"] == "text"
    settings.STUDIO_QUOTA_DEFAULTS = {
        **settings.STUDIO_QUOTA_DEFAULTS,
        "max_custom_fields_per_entity": 2,
    }
    over = owner.post(f"{V1}/fields/", {**body, "key": "third"})
    assert over.status_code == 400
    assert any(e["field"] == "quota" for e in over.json()["errors"])

    path = f"/api/v1/institutions/{org.north.pk}/"
    updated = owner.patch(path, {"extra": {"founded": 1998, "bank_ref": "X-1"}})
    assert updated.status_code == 200, updated.content
    assert updated.json()["extra"] == {"founded": 1998, "bank_ref": "X-1"}
    assert owner.patch(path, {"extra": {"founded": "old"}}).status_code == 400
    assert owner.patch(path, {"extra": {"nope": 1}}).status_code == 400
    head = _member(org, "h@example.com", "institution_admin", institution=org.north)
    assert head.get(path).json()["extra"] == {"founded": 1998}  # bank_ref is masked
    cleared = owner.patch(path, {"extra": {"bank_ref": None}})
    assert cleared.json()["extra"] == {"founded": 1998}
    deprecated = owner.post(f"{V1}/fields/{created['id']}/deprecate/")
    assert deprecated.json()["deprecated_at"] is not None


def test_rules_forms_workflows_templates_and_numbering(org):
    owner = _member(org, "o@example.com", "tenant_owner")
    rule = {">=": [{"var": "field.age"}, 18]}
    tested = owner.post(
        f"{V1}/rules/test/",
        {
            "namespace": "customization.form_visibility",
            "rule": rule,
            "test_cases": [{"context": {"field.age": 20}, "expected": True}],
        },
    )
    assert tested.json()["results"][0]["passed"] is True
    assert (
        owner.post(
            f"{V1}/rules/test/",
            {"namespace": "customization.form_visibility", "rule": {"eval": [1]}, "test_cases": []},
        ).status_code
        == 400
    )
    owner.post(
        f"{V1}/rules/",
        {
            "namespace": "customization.form_visibility",
            "key": "adult",
            "name": "Adult",
            "rule": rule,
            "test_cases": [{"context": {"field.age": 20}, "expected": True}],
        },
    )
    assert owner.post(f"{V1}/rules/adult/publish/").json()["status"] == "published"
    listing = owner.get(f"{V1}/rules/").json()
    assert listing["quota"]["used"] == 1 and listing["items"][0]["key"] == "adult"

    layout = {
        "sections": [
            {
                "key": "basic",
                "labels": {"en": "Basic"},
                "fields": [{"source": "core", "name": "name", "required": True}],
            }
        ]
    }
    assert (
        owner.post(
            f"{V1}/forms/",
            {"key": "inst", "entity": "tenancy.institution", "name": "Inst", "layout": layout},
        ).status_code
        == 201
    )
    owner.post(f"{V1}/forms/inst/publish/")
    assert owner.get(f"{V1}/forms/inst/render/").json()["sections"][0]["key"] == "basic"
    assert owner.post(f"{V1}/forms/inst/visibility/", {"values": {}}).json()["sections"] == [
        "basic"
    ]
    invalid = owner.post(f"{V1}/forms/inst/validate/", {"values": {}})
    assert invalid.status_code == 400 and any(
        e["field"] == "name" for e in invalid.json()["errors"]
    )
    assert owner.post(f"{V1}/forms/inst/validate/", {"values": {"name": "N"}}).json()["core"] == {
        "name": "N"
    }

    spec = {
        "states": [
            {"key": "open", "labels": {"en": "Open"}},
            {"key": "done", "labels": {"en": "Done"}, "final": True},
        ],
        "initial": "open",
        "start_permission": "tenancy.member.view",
        "transitions": [
            {
                "key": "close",
                "from": ["open"],
                "to": "done",
                "labels": {"en": "Close"},
                "permission": "tenancy.member.update",
            }
        ],
    }
    owner.post(
        f"{V1}/workflows/",
        {"key": "review", "subject": "tenancy.member", "name": "Review", "spec": spec},
    )
    owner.post(f"{V1}/workflows/review/publish/")
    started = owner.post(f"{V1}/workflows/review/start/", {"subject_id": str(uuid.uuid4())}).json()
    assert started["state"] == "open" and started["actions"] == ["close"]
    moved = owner.post(
        f"{V1}/workflow-requests/{started['id']}/transition/", {"transition": "close", "note": "ok"}
    )
    assert moved.json()["state"] == "done" and moved.json()["steps"][0]["note"] == "ok"
    teacher = _member(org, "t@example.com", "teacher", institution=org.north, campus=org.main)
    assert teacher.post(
        f"{V1}/workflows/review/start/", {"subject_id": str(uuid.uuid4())}
    ).status_code in (400, 403)

    content = {"en": {"body": "Hello {{ recipient }}"}}
    preview = owner.post(
        f"{V1}/templates/preview/",
        {"kind": "customization.sms", "content": content, "locale": "en"},
    )
    assert preview.json()["body"] == "Hello A. Rahman"
    escape = owner.post(
        f"{V1}/templates/preview/",
        {
            "kind": "customization.sms",
            "content": {"en": {"body": "{{ ''.__class__ }}"}},
            "locale": "en",
        },
    )
    assert escape.status_code == 400
    owner.post(
        f"{V1}/templates/",
        {"key": "hello", "kind": "customization.sms", "name": "Hello", "content": content},
    )
    assert owner.post(f"{V1}/templates/hello/publish/").json()["status"] == "published"

    assert (
        owner.post(
            f"{V1}/numbering/", {"key": "receipt", "name": "R", "pattern": "R-{SEQ:4}"}
        ).status_code
        == 201
    )
    assert (
        owner.post(
            f"{V1}/numbering/", {"key": "bad", "name": "B", "pattern": "R {SEQ:4}"}
        ).status_code
        == 400
    )
    assert [r["key"] for r in owner.get(f"{V1}/numbering/").json()] == ["receipt"]

    inbox = owner.get("/api/v1/notifications/").json()
    assert inbox["unread"] >= 1
    ids = [n["id"] for n in inbox["items"]]
    assert owner.post("/api/v1/notifications/read/", {"ids": ids}).json()["unread"] == 0


def test_platform_presets_are_listed_on_the_platform_host(admin_api, org):
    rows = admin_api.get("/api/v1/platform/presets/").json()
    assert {r["institution_type"] for r in rows} >= {"school", "madrasa", "university"}
    plain = Api()
    plain.login(make_user("plain@example.com"), expect="authenticated")
    assert plain.get("/api/v1/platform/presets/").status_code == 403
