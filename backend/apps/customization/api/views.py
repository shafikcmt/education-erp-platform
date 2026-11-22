"""Customization Studio API (Phase 5 M6; plan §9). Tenant host only.

Views translate requests into service calls; the services check every permission in the exact
scope (uncached), validate content (sandboxes, schemas), enforce quotas and write the audit.
The permission classes here are the first gate (module ``customization``; the codes' flags add
MFA and, for publishing, a fresh step-up).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.hosts import PLATFORM_ONLY
from apps.customization import (
    fields,
    forms,
    numbering,
    quotas,
    rule_services,
    services,
    template_services,
    workflows,
)
from apps.customization.api import serializers as s
from apps.customization.models import (
    ConfigVersion,
    FieldDefinition,
    FormDefinition,
    NumberingSequence,
    Preset,
    RuleDefinition,
    TemplateDefinition,
    WorkflowDefinition,
    WorkflowInstance,
)
from apps.customization.registry import (
    declared_entities,
    declared_namespaces,
    declared_settings,
    declared_subjects,
    declared_template_kinds,
    entity_core_fields,
)
from apps.customization.resolver import effective_config
from apps.customization.rules import RuleError, check
from apps.customization.scopes import ConfigScope
from apps.identity.api.utils import CsrfProtectedView, get_or_404, service_errors
from apps.identity.models import User
from apps.rbac.engine import has_perm
from apps.rbac.permissions import HasPermission
from apps.tenancy.api.permissions import HasTenantAnyPermission, HasTenantPermission
from apps.tenancy.api.views_tenant import TenantView

TAGS = ["studio"]
OWN = "identity.account.view_own"  # signed-in member; the service checks the real permission


def _actor(request: Request) -> User:
    assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
    return request.user


def _valid(serializer: Any, data: Any) -> dict[str, Any]:
    form = serializer(data=data)
    form.is_valid(raise_exception=True)
    return dict(form.validated_data)


def _scope(values: dict[str, Any]) -> ConfigScope:
    try:
        return ConfigScope(values.get("institution"), values.get("campus"))
    except ValueError as exc:
        raise ValidationError({"scope": str(exc)}) from None


class StudioView(TenantView):
    module_code = "customization"


# --------------------------------------------------------------------------- catalogue
class CatalogView(StudioView):
    permission_classes = [
        HasTenantAnyPermission("customization.config.view", "customization.field.view")
    ]

    @extend_schema(
        tags=TAGS, summary="What the Studio can configure", responses=s.CatalogSerializer
    )
    def get(self, request: Request) -> Response:
        quota_counts = {
            "max_forms": FormDefinition.objects.values("key").distinct().count(),
            "max_workflows": WorkflowDefinition.objects.values("key").distinct().count(),
            "max_rules": RuleDefinition.objects.values("key").distinct().count(),
            "max_templates": TemplateDefinition.objects.values("key").distinct().count(),
        }
        data = {
            "settings": {
                key: {
                    "schema": spec.schema,
                    "default": spec.default,
                    "scopes": list(spec.scopes),
                    "description": spec.description,
                }
                for key, spec in declared_settings().items()
            },
            "entities": declared_entities(),
            "core_fields": {k: sorted(v) for k, v in entity_core_fields().items()},
            "rule_namespaces": {
                code: {
                    "variables": list(ns.variables),
                    "result": ns.result,
                    "description": ns.description,
                }
                for code, ns in declared_namespaces().items()
            },
            "template_kinds": {
                code: {k: v for k, v in kind.items() if k != "sample"}
                for code, kind in declared_template_kinds().items()
            },
            "workflow_subjects": declared_subjects(),
            "quotas": {key: quotas.status(key, used) for key, used in quota_counts.items()},
        }
        return Response(s.CatalogSerializer(data).data)


# --------------------------------------------------------------------------- configuration
def _version(row: ConfigVersion | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "number": row.number,
        "status": row.status,
        "data": row.data,
        "note": row.note,
        "published_at": row.published_at,
        "based_on": row.based_on,
    }


def _config_state(scope: ConfigScope) -> dict[str, Any]:
    rows = list(ConfigVersion.objects.filter(**scope.filters()).order_by("-number"))
    return {
        "scope": scope.kind,
        "published": _version(next((r for r in rows if r.status == "published"), None)),
        "draft": _version(next((r for r in rows if r.status == "draft"), None)),
        "effective": effective_config(scope),
        "history": [_version(r) for r in rows if r.status != "draft"],
    }


SCOPE_PARAMS = [
    OpenApiParameter("institution", OpenApiTypes.UUID),
    OpenApiParameter("campus", OpenApiTypes.UUID),
]


class ConfigView(StudioView):
    permission_classes = [
        HasTenantPermission(
            {
                "GET": "customization.config.view",
                "PUT": "customization.config.edit",
                "DELETE": "customization.config.edit",
            }
        )
    ]

    @extend_schema(
        tags=TAGS,
        summary="Configuration of a scope",
        parameters=SCOPE_PARAMS,
        responses=s.ConfigStateSerializer,
    )
    def get(self, request: Request) -> Response:
        scope = _scope(_valid(s.ScopeQuerySerializer, request.query_params))
        if not has_perm(request.user, "customization.config.view", target=scope.target()):
            raise NotFound()  # outside the viewer's scopes: indistinguishable from unknown
        return Response(s.ConfigStateSerializer(_config_state(scope)).data)

    @extend_schema(
        tags=TAGS,
        summary="Save the draft",
        request=s.ConfigDraftSerializer,
        responses=s.ConfigStateSerializer,
    )
    def put(self, request: Request) -> Response:
        values = _valid(s.ConfigDraftSerializer, request.data)
        scope = _scope(values)
        with service_errors():
            services.save_draft(
                actor=_actor(request),
                scope=scope,
                data=values["data"],
                note=values["note"],
                request=request,
            )
        return Response(s.ConfigStateSerializer(_config_state(scope)).data)

    @extend_schema(
        tags=TAGS, summary="Discard the draft", parameters=SCOPE_PARAMS, responses={204: None}
    )
    def delete(self, request: Request) -> Response:
        scope = _scope(_valid(s.ScopeQuerySerializer, request.query_params))
        with service_errors():
            services.discard_draft(actor=_actor(request), scope=scope, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConfigPublishView(StudioView):
    permission_classes = [HasTenantPermission({"POST": "customization.config.publish"})]

    @extend_schema(
        tags=TAGS,
        summary="Publish the draft",
        request=s.ConfigPublishSerializer,
        responses=s.ConfigStateSerializer,
    )
    def post(self, request: Request) -> Response:
        values = _valid(s.ConfigPublishSerializer, request.data)
        scope = _scope(values)
        with service_errors():
            services.publish(
                actor=_actor(request), scope=scope, note=values["note"], request=request
            )
        return Response(s.ConfigStateSerializer(_config_state(scope)).data)


class ConfigRollbackView(StudioView):
    permission_classes = [HasTenantPermission({"POST": "customization.config.publish"})]

    @extend_schema(
        tags=TAGS,
        summary="Publish a copy of an earlier version",
        request=s.ConfigRollbackSerializer,
        responses=s.ConfigStateSerializer,
    )
    def post(self, request: Request) -> Response:
        values = _valid(s.ConfigRollbackSerializer, request.data)
        scope = _scope(values)
        with service_errors():
            services.rollback(
                actor=_actor(request),
                scope=scope,
                number=values["number"],
                note=values["note"],
                request=request,
            )
        return Response(s.ConfigStateSerializer(_config_state(scope)).data)


# --------------------------------------------------------------------------- custom fields
FIELD_ATTRS = (
    "id", "entity", "key", "field_type", "labels", "required", "options", "validation",
    "visibility", "view_permission", "edit_permission", "pii", "order", "deprecated_at",
)  # fmt: skip


def _field(row: FieldDefinition) -> dict[str, Any]:
    return {name: getattr(row, name) for name in FIELD_ATTRS}


class FieldsView(StudioView):
    permission_classes = [
        HasPermission({"GET": "customization.field.view", "POST": "customization.field.manage"})
    ]

    @extend_schema(
        tags=TAGS,
        summary="Custom field definitions",
        parameters=[OpenApiParameter("entity", OpenApiTypes.STR)],
        responses=s.FieldSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        rows = FieldDefinition.objects.order_by("entity", "order", "key")
        if entity := request.query_params.get("entity"):
            rows = rows.filter(entity=entity[:80])
        return Response(s.FieldSerializer([_field(r) for r in rows], many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Define a custom field",
        request=s.FieldCreateSerializer,
        responses={201: s.FieldSerializer},
    )
    def post(self, request: Request) -> Response:
        values = _valid(s.FieldCreateSerializer, request.data)
        with service_errors():
            row = fields.define_field(actor=_actor(request), request=request, **values)
        return Response(s.FieldSerializer(_field(row)).data, status=status.HTTP_201_CREATED)


class FieldDetailView(StudioView):
    permission_classes = [HasPermission({"PATCH": "customization.field.manage"})]

    @extend_schema(
        tags=TAGS,
        summary="Change a custom field (never its key or type)",
        request=s.FieldUpdateSerializer,
        responses=s.FieldSerializer,
    )
    def patch(self, request: Request, field_id: str) -> Response:
        row = get_or_404(FieldDefinition.objects.all(), field_id)
        values = _valid(s.FieldUpdateSerializer, request.data)
        with service_errors():
            row = fields.update_field(
                actor=_actor(request), field=row, changes=values, request=request
            )
        return Response(s.FieldSerializer(_field(row)).data)


class FieldDeprecateView(StudioView):
    permission_classes = [HasPermission({"POST": "customization.field.manage"})]

    @extend_schema(
        tags=TAGS, summary="Deprecate a custom field", request=None, responses=s.FieldSerializer
    )
    def post(self, request: Request, field_id: str) -> Response:
        row = get_or_404(FieldDefinition.objects.all(), field_id)
        with service_errors():
            row = fields.deprecate_field(actor=_actor(request), field=row, request=request)
        return Response(s.FieldSerializer(_field(row)).data)


# --------------------------------------------------------------------------- versioned artefacts
def _artefact(row: Any, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.pk,
        "key": row.key,
        "name": row.name,
        "number": row.number,
        "status": row.status,
        "published_at": row.published_at,
        "body": body,
    }


def _listing(model: Any, quota_key: str, body: Any) -> Response:
    rows = list(model.objects.order_by("key", "-number"))
    data = {
        "items": [_artefact(r, body(r)) for r in rows],
        "quota": quotas.status(quota_key, len({r.key for r in rows})),
    }
    return Response(s.ArtefactListSerializer(data).data)


def _rule_body(r: RuleDefinition) -> dict[str, Any]:
    return {"namespace": r.namespace, "rule": r.rule, "test_cases": r.test_cases}


def _form_body(r: FormDefinition) -> dict[str, Any]:
    return {"entity": r.entity, "layout": r.layout}


def _workflow_body(r: WorkflowDefinition) -> dict[str, Any]:
    return {"subject": r.subject, "spec": r.spec}


def _template_body(r: TemplateDefinition) -> dict[str, Any]:
    return {"kind": r.kind, "content": r.content}


class RulesView(StudioView):
    permission_classes = [
        HasPermission({"GET": "customization.rule.view", "POST": "customization.rule.manage"})
    ]

    @extend_schema(tags=TAGS, summary="Rules (every version)", responses=s.ArtefactListSerializer)
    def get(self, request: Request) -> Response:
        return _listing(RuleDefinition, "max_rules", _rule_body)

    @extend_schema(
        tags=TAGS,
        summary="Save a rule draft",
        request=s.RuleDraftSerializer,
        responses={201: s.ArtefactSerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.RuleDraftSerializer, request.data)
        with service_errors():
            row = rule_services.save_rule_draft(
                actor=_actor(request),
                namespace_code=v["namespace"],
                key=v["key"],
                name=v["name"],
                rule=v["rule"],
                test_cases=v.get("test_cases", []),
                request=request,
            )
        return Response(
            s.ArtefactSerializer(_artefact(row, _rule_body(row))).data,
            status=status.HTTP_201_CREATED,
        )


class RuleTestView(StudioView):
    permission_classes = [HasPermission({"POST": "customization.rule.manage"})]

    @extend_schema(
        tags=TAGS,
        summary="Test a rule with sample data",
        request=s.RuleTestSerializer,
        responses=s.RuleTestResultSerializer,
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.RuleTestSerializer, request.data)
        with service_errors():
            spec = rule_services.namespace(v["namespace"])
            cases = rule_services._check_cases(v["test_cases"])
            try:
                check(v["rule"], spec)  # always: even without test cases
                results = rule_services.run_cases(spec, v["rule"], cases)
            except RuleError as exc:
                raise ValidationError({"rule": str(exc)}) from None
        for item in results:  # Decimal results travel as strings
            if item["result"] is not None and not isinstance(item["result"], bool | str):
                item["result"] = str(item["result"])
        return Response(s.RuleTestResultSerializer({"results": results}).data)


def _publish_view(publish: Any, body: Any, label: str) -> type[StudioView]:
    class View(StudioView):
        permission_classes = [HasPermission({"POST": "customization.config.publish"})]

        @extend_schema(
            tags=TAGS,
            summary=f"Publish a {label} draft",
            request=None,
            responses=s.ArtefactSerializer,
            operation_id=f"studio_{label}_publish",
        )
        def post(self, request: Request, key: str) -> Response:
            with service_errors():
                row = publish(actor=_actor(request), key=key[:64], request=request)
            return Response(s.ArtefactSerializer(_artefact(row, body(row))).data)

    View.__name__ = View.__qualname__ = f"{label.title()}PublishView"
    return View


RulePublishView = _publish_view(rule_services.publish_rule, _rule_body, "rule")
FormPublishView = _publish_view(forms.publish_form, _form_body, "form")
WorkflowPublishView = _publish_view(workflows.publish_workflow, _workflow_body, "workflow")
TemplatePublishView = _publish_view(template_services.publish_template, _template_body, "template")


class FormsView(StudioView):
    permission_classes = [
        HasPermission({"GET": "customization.form.view", "POST": "customization.form.manage"})
    ]

    @extend_schema(tags=TAGS, summary="Forms (every version)", responses=s.ArtefactListSerializer)
    def get(self, request: Request) -> Response:
        return _listing(FormDefinition, "max_forms", _form_body)

    @extend_schema(
        tags=TAGS,
        summary="Save a form draft",
        request=s.FormDraftSerializer,
        responses={201: s.ArtefactSerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.FormDraftSerializer, request.data)
        with service_errors():
            row = forms.save_form_draft(actor=_actor(request), request=request, **v)
        return Response(
            s.ArtefactSerializer(_artefact(row, _form_body(row))).data,
            status=status.HTTP_201_CREATED,
        )


class FormRenderView(StudioView):
    permission_classes = [HasPermission({"GET": "customization.form.view"})]

    @extend_schema(
        tags=TAGS, summary="Published form for the renderer", responses=OpenApiTypes.OBJECT
    )
    def get(self, request: Request, key: str) -> Response:
        with service_errors():
            return Response(forms.render(key[:64]))


class FormVisibilityView(StudioView):
    permission_classes = [HasPermission({"POST": "customization.form.view"})]

    @extend_schema(
        tags=TAGS,
        summary="Sections visible for these values",
        request=s.FormValuesSerializer,
        responses=s.FormVisibilitySerializer,
    )
    def post(self, request: Request, key: str) -> Response:
        v = _valid(s.FormValuesSerializer, request.data)
        with service_errors():
            shown = forms.visible_sections(key[:64], v["values"])
        return Response(s.FormVisibilitySerializer({"sections": shown}).data)


class FormValidateView(StudioView):
    permission_classes = [HasPermission({"POST": "customization.form.view"})]

    @extend_schema(
        tags=TAGS,
        summary="Validate a submission (server-side)",
        request=s.FormValuesSerializer,
        responses=s.FormValidatedSerializer,
    )
    def post(self, request: Request, key: str) -> Response:
        v = _valid(s.FormValuesSerializer, request.data)
        with service_errors():
            cleaned = forms.validate_submission(key[:64], v["values"])
        return Response(s.FormValidatedSerializer(cleaned).data)


class WorkflowsView(StudioView):
    permission_classes = [
        HasPermission(
            {"GET": "customization.workflow.view", "POST": "customization.workflow.manage"}
        )
    ]

    @extend_schema(
        tags=TAGS, summary="Workflows (every version)", responses=s.ArtefactListSerializer
    )
    def get(self, request: Request) -> Response:
        return _listing(WorkflowDefinition, "max_workflows", _workflow_body)

    @extend_schema(
        tags=TAGS,
        summary="Save a workflow draft",
        request=s.WorkflowDraftSerializer,
        responses={201: s.ArtefactSerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.WorkflowDraftSerializer, request.data)
        with service_errors():
            row = workflows.save_workflow_draft(actor=_actor(request), request=request, **v)
        return Response(
            s.ArtefactSerializer(_artefact(row, _workflow_body(row))).data,
            status=status.HTTP_201_CREATED,
        )


def _instance(instance: WorkflowInstance) -> dict[str, Any]:
    definition = WorkflowDefinition.objects.get(pk=instance.definition_id)
    actions = (
        [t["key"] for t in definition.spec["transitions"] if instance.state in t["from"]]
        if instance.finished_at is None
        else []
    )
    return {
        "id": instance.pk,
        "workflow": definition.key,
        "version": definition.number,
        "subject": instance.subject,
        "subject_id": instance.subject_id,
        "state": instance.state,
        "sla_due_at": instance.sla_due_at,
        "sla_breached_at": instance.sla_breached_at,
        "finished_at": instance.finished_at,
        "actions": actions,
        "steps": list(
            instance.steps.order_by("created_at").values(
                "transition", "from_state", "to_state", "note", "created_at"
            )
        ),
    }


class WorkflowStartView(StudioView):
    permission_classes = [HasPermission({"POST": OWN})]

    @extend_schema(
        tags=TAGS,
        summary="Start a request (needs the workflow's start permission)",
        request=s.WorkflowStartSerializer,
        responses={201: s.WorkflowInstanceSerializer},
    )
    def post(self, request: Request, key: str) -> Response:
        v = _valid(s.WorkflowStartSerializer, request.data)
        with service_errors():
            instance = workflows.start(
                actor=_actor(request),
                key=key[:64],
                subject_id=v["subject_id"],
                context=v.get("context") or {},
                request=request,
            )
        return Response(
            s.WorkflowInstanceSerializer(_instance(instance)).data, status=status.HTTP_201_CREATED
        )


class WorkflowRequestView(StudioView):
    permission_classes = [HasPermission({"GET": "customization.workflow.view"})]

    @extend_schema(
        tags=TAGS, summary="A request and its history", responses=s.WorkflowInstanceSerializer
    )
    def get(self, request: Request, instance_id: str) -> Response:
        instance = get_or_404(WorkflowInstance.objects.all(), instance_id)
        return Response(s.WorkflowInstanceSerializer(_instance(instance)).data)


class WorkflowTransitionView(StudioView):
    permission_classes = [HasPermission({"POST": OWN})]

    @extend_schema(
        tags=TAGS,
        summary="Act on a request (needs the action's permission)",
        request=s.WorkflowTransitionSerializer,
        responses=s.WorkflowInstanceSerializer,
    )
    def post(self, request: Request, instance_id: str) -> Response:
        v = _valid(s.WorkflowTransitionSerializer, request.data)
        try:
            pk = uuid.UUID(instance_id)
        except ValueError:
            raise NotFound() from None
        with service_errors():
            instance = workflows.transition(
                actor=_actor(request),
                instance_id=pk,
                transition_key=v["transition"],
                note=v["note"],
                request=request,
            )
        return Response(s.WorkflowInstanceSerializer(_instance(instance)).data)


class TemplatesView(StudioView):
    permission_classes = [
        HasPermission(
            {"GET": "customization.template.view", "POST": "customization.template.manage"}
        )
    ]

    @extend_schema(
        tags=TAGS, summary="Templates (every version)", responses=s.ArtefactListSerializer
    )
    def get(self, request: Request) -> Response:
        return _listing(TemplateDefinition, "max_templates", _template_body)

    @extend_schema(
        tags=TAGS,
        summary="Save a template draft",
        request=s.TemplateDraftSerializer,
        responses={201: s.ArtefactSerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.TemplateDraftSerializer, request.data)
        with service_errors():
            row = template_services.save_template_draft(
                actor=_actor(request),
                key=v["key"],
                kind_code=v["kind"],
                name=v["name"],
                content=v["content"],
                request=request,
            )
        return Response(
            s.ArtefactSerializer(_artefact(row, _template_body(row))).data,
            status=status.HTTP_201_CREATED,
        )


class TemplatePreviewView(StudioView):
    permission_classes = [HasPermission({"POST": "customization.template.manage"})]

    @extend_schema(
        tags=TAGS,
        summary="Preview a template",
        request=s.TemplatePreviewSerializer,
        responses=s.TemplateRenderedSerializer,
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.TemplatePreviewSerializer, request.data)
        with service_errors():
            out = template_services.preview(
                kind_code=v["kind"], content=v["content"], locale=v["locale"], data=v.get("data")
            )
        return Response(s.TemplateRenderedSerializer(out).data)


class SequencesView(StudioView):
    permission_classes = [
        HasPermission(
            {"GET": "customization.numbering.view", "POST": "customization.numbering.manage"}
        )
    ]

    @extend_schema(
        tags=TAGS, summary="Numbering sequences", responses=s.SequenceSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        rows = NumberingSequence.objects.filter(archived_at__isnull=True).order_by("key")
        return Response(s.SequenceSerializer(rows, many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Define a numbering sequence",
        request=s.SequenceCreateSerializer,
        responses={201: s.SequenceSerializer},
    )
    def post(self, request: Request) -> Response:
        v = _valid(s.SequenceCreateSerializer, request.data)
        with service_errors():
            row = numbering.define_sequence(actor=_actor(request), request=request, **v)
        return Response(s.SequenceSerializer(row).data, status=status.HTTP_201_CREATED)


# --------------------------------------------------------------------------- platform host
class PlatformPresetsView(CsrfProtectedView):
    host_classes = PLATFORM_ONLY
    permission_classes = [HasPermission({"GET": "tenancy.tenant.view_any"})]
    platform_operations = {"GET": "P8"}

    @extend_schema(
        tags=["platform-tenants"],
        summary="Institution-type presets",
        responses=s.PresetSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        rows = Preset.objects.filter(deprecated_at__isnull=True).order_by(
            "institution_type", "code"
        )
        return Response(s.PresetSerializer(rows, many=True).data)
