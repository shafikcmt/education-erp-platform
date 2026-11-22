"""Serializers of the Studio API (Phase 5 M6). Artefact bodies are JSON validated by the
services (the sandboxes and schema checks live there, not here)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

JSON = serializers.JSONField


class ScopeQuerySerializer(serializers.Serializer[Any]):
    institution = serializers.UUIDField(required=False, allow_null=True)
    campus = serializers.UUIDField(required=False, allow_null=True)


class ConfigVersionSerializer(serializers.Serializer[Any]):
    number = serializers.IntegerField()
    status = serializers.CharField()
    data = JSON()  # type: ignore[assignment]  # field name shadows a DRF attribute
    note = serializers.CharField()
    published_at = serializers.DateTimeField(allow_null=True)
    based_on = serializers.IntegerField(allow_null=True)


class ConfigStateSerializer(serializers.Serializer[Any]):
    scope = serializers.CharField()
    published = ConfigVersionSerializer(allow_null=True)
    draft = ConfigVersionSerializer(allow_null=True)
    effective = JSON()
    history = ConfigVersionSerializer(many=True)


class ConfigDraftSerializer(ScopeQuerySerializer):
    data = serializers.DictField()  # type: ignore[assignment]  # field name shadows a DRF attribute
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class ConfigPublishSerializer(ScopeQuerySerializer):
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class ConfigRollbackSerializer(ScopeQuerySerializer):
    number = serializers.IntegerField(min_value=1)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class CatalogSerializer(serializers.Serializer[Any]):
    settings = JSON()
    entities = JSON()
    core_fields = JSON()
    rule_namespaces = JSON()
    template_kinds = JSON()
    workflow_subjects = JSON()
    quotas = JSON()


class FieldSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    entity = serializers.CharField()
    key = serializers.CharField()
    field_type = serializers.CharField()
    labels = JSON()
    required = serializers.BooleanField()  # type: ignore[assignment]  # field name shadows a DRF attribute
    options = JSON()
    validation = JSON()
    visibility = serializers.CharField()
    view_permission = serializers.CharField()
    edit_permission = serializers.CharField()
    pii = serializers.BooleanField()
    order = serializers.IntegerField()
    deprecated_at = serializers.DateTimeField(allow_null=True)


class FieldCreateSerializer(serializers.Serializer[Any]):
    entity = serializers.CharField(max_length=80)
    key = serializers.CharField(max_length=64)
    field_type = serializers.CharField(max_length=16)
    labels = serializers.DictField()
    required = serializers.BooleanField(required=False)  # type: ignore[assignment]  # field name shadows a DRF attribute
    options = serializers.ListField(required=False)
    validation = serializers.DictField(required=False)
    visibility = serializers.CharField(required=False)
    view_permission = serializers.CharField(required=False, allow_blank=True)
    edit_permission = serializers.CharField(required=False, allow_blank=True)
    pii = serializers.BooleanField(required=False)
    order = serializers.IntegerField(required=False, min_value=0, max_value=1000)


class FieldUpdateSerializer(serializers.Serializer[Any]):
    labels = serializers.DictField(required=False)
    required = serializers.BooleanField(required=False)  # type: ignore[assignment]  # field name shadows a DRF attribute
    options = serializers.ListField(required=False)
    validation = serializers.DictField(required=False)
    visibility = serializers.CharField(required=False)
    view_permission = serializers.CharField(required=False, allow_blank=True)
    edit_permission = serializers.CharField(required=False, allow_blank=True)
    pii = serializers.BooleanField(required=False)
    order = serializers.IntegerField(required=False, min_value=0, max_value=1000)


class ArtefactSerializer(serializers.Serializer[Any]):
    """A version of a rule, form, workflow or template."""

    id = serializers.UUIDField()
    key = serializers.CharField()
    name = serializers.CharField()
    number = serializers.IntegerField()
    status = serializers.CharField()
    published_at = serializers.DateTimeField(allow_null=True)
    body = JSON()


class ArtefactListSerializer(serializers.Serializer[Any]):
    items = ArtefactSerializer(many=True)
    quota = JSON()


class RuleDraftSerializer(serializers.Serializer[Any]):
    namespace = serializers.CharField(max_length=80)
    key = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=120)
    rule = JSON()
    test_cases = serializers.ListField(required=False)


class RuleTestSerializer(serializers.Serializer[Any]):
    namespace = serializers.CharField(max_length=80)
    rule = JSON()
    test_cases = serializers.ListField()


class RuleTestResultSerializer(serializers.Serializer[Any]):
    results = JSON()


class FormDraftSerializer(serializers.Serializer[Any]):
    key = serializers.CharField(max_length=64)
    entity = serializers.CharField(max_length=80)
    name = serializers.CharField(max_length=120)
    layout = JSON()


class FormValuesSerializer(serializers.Serializer[Any]):
    values = serializers.DictField()


class FormVisibilitySerializer(serializers.Serializer[Any]):
    sections = serializers.ListField(child=serializers.CharField())


class FormValidatedSerializer(serializers.Serializer[Any]):
    core = JSON()
    custom = JSON()


class WorkflowDraftSerializer(serializers.Serializer[Any]):
    key = serializers.CharField(max_length=64)
    subject = serializers.CharField(max_length=80)
    name = serializers.CharField(max_length=120)
    spec = JSON()


class WorkflowStartSerializer(serializers.Serializer[Any]):
    subject_id = serializers.UUIDField()
    context = serializers.DictField(required=False)  # type: ignore[assignment]  # field name shadows a DRF attribute


class WorkflowTransitionSerializer(serializers.Serializer[Any]):
    transition = serializers.CharField(max_length=40)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class WorkflowStepSerializer(serializers.Serializer[Any]):
    transition = serializers.CharField()
    from_state = serializers.CharField()
    to_state = serializers.CharField()
    note = serializers.CharField()
    created_at = serializers.DateTimeField()


class WorkflowInstanceSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    workflow = serializers.CharField()
    version = serializers.IntegerField()
    subject = serializers.CharField()
    subject_id = serializers.UUIDField()
    state = serializers.CharField()
    sla_due_at = serializers.DateTimeField(allow_null=True)
    sla_breached_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    actions = serializers.ListField(child=serializers.CharField())
    steps = WorkflowStepSerializer(many=True)


class TemplateDraftSerializer(serializers.Serializer[Any]):
    key = serializers.CharField(max_length=64)
    kind = serializers.CharField(max_length=80)
    name = serializers.CharField(max_length=120)
    content = serializers.DictField()


class TemplatePreviewSerializer(serializers.Serializer[Any]):
    kind = serializers.CharField(max_length=80)
    content = serializers.DictField()
    locale = serializers.CharField(max_length=5)
    data = serializers.DictField(required=False)  # type: ignore[assignment]  # field name shadows a DRF attribute


class TemplateRenderedSerializer(serializers.Serializer[Any]):
    body = serializers.CharField()
    subject = serializers.CharField(required=False)


class SequenceSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    key = serializers.CharField()
    name = serializers.CharField()
    pattern = serializers.CharField()
    scope = serializers.CharField()
    reset = serializers.CharField()


class SequenceCreateSerializer(serializers.Serializer[Any]):
    key = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=120)
    pattern = serializers.CharField(max_length=64)
    scope = serializers.CharField(required=False, default="tenant")
    reset = serializers.CharField(required=False, default="never")


class PresetSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    institution_type = serializers.CharField()
    version = serializers.IntegerField()
    is_default = serializers.BooleanField()
    name = JSON()
    content = JSON()
