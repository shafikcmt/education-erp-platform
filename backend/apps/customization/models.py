"""Configuration versions (Phase 5 M1; ADR-057).

One row per version of one scope of a tenant: the whole tenant, one institution or one campus.
``draft`` is editable and seen only in preview; ``published`` is the active, immutable version
(at most one per scope); ``archived`` versions stay for history and rollback. Tenant-owned
(standard RLS); the institution and campus references are composite ``(tenant_id, …)`` keys
in the database (``customization.0002``), so another tenant's scope can never be referenced.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel
from apps.core.tenancy.models import TenantScopedModel


class ConfigVersion(TenantScopedModel):
    class Scope(models.TextChoices):
        TENANT = "tenant", "Tenant"
        INSTITUTION = "institution", "Institution"
        CAMPUS = "campus", "Campus"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    scope_type = models.CharField(max_length=16, choices=Scope.choices)
    institution = models.ForeignKey(
        "tenancy.Institution",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        db_constraint=False,
    )
    campus = models.ForeignKey(
        "tenancy.Campus",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        db_constraint=False,
    )
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    data = models.JSONField(default=dict, blank=True)
    note = models.CharField(max_length=200, blank=True, default="")
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.UUIDField(null=True, blank=True)
    based_on = models.PositiveIntegerField(null=True, blank=True)  # rollback source number

    class Meta(TenantScopedModel.Meta):
        db_table = "customization_configversion"
        ordering = ("-number",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope_type="tenant", institution__isnull=True, campus__isnull=True)
                    | models.Q(
                        scope_type="institution", institution__isnull=False, campus__isnull=True
                    )
                    | models.Q(scope_type="campus", institution__isnull=False, campus__isnull=False)
                ),
                name="customization_config_scope",
            ),
            models.UniqueConstraint(
                fields=["tenant", "scope_type", "institution", "campus", "number"],
                nulls_distinct=False,
                name="customization_config_number_unique",
            ),
            models.UniqueConstraint(
                fields=["tenant", "scope_type", "institution", "campus"],
                condition=models.Q(status="draft"),
                nulls_distinct=False,
                name="customization_config_one_draft",
            ),
            models.UniqueConstraint(
                fields=["tenant", "scope_type", "institution", "campus"],
                condition=models.Q(status="published"),
                nulls_distinct=False,
                name="customization_config_one_published",
            ),
        ]

    def __str__(self) -> str:
        return f"config {self.scope_type} v{self.number} ({self.status})"


class Preset(BaseModel):
    """Synced institution-type preset (platform registry, no tenant data; owner-written)."""

    code = models.CharField(max_length=64, unique=True)
    institution_type = models.CharField(max_length=32)
    version = models.PositiveIntegerField()
    is_default = models.BooleanField(default=False)
    name = models.JSONField(default=dict)
    content = models.JSONField(default=dict)  # suggested_modules + settings
    checksum = models.CharField(max_length=64)
    deprecated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "customization_preset"
        ordering = ("institution_type", "code")
        constraints = [
            models.UniqueConstraint(
                fields=["institution_type"],
                condition=models.Q(is_default=True, deprecated_at__isnull=True),
                name="customization_preset_one_default",
            )
        ]

    def __str__(self) -> str:
        return self.code


class Lifecycle(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class RuleDefinition(TenantScopedModel):
    """A versioned rule (ADR-055): a JSON AST of a declared namespace with its test cases.
    Publishing runs every test case; published versions are immutable."""

    namespace = models.CharField(max_length=80)
    key = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    rule = models.JSONField()
    test_cases = models.JSONField(default=list, blank=True)
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Lifecycle.choices, default=Lifecycle.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.UUIDField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "customization_ruledefinition"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(key__regex=r"^[a-z][a-z0-9_]{1,63}$"),
                name="customization_rule_key_valid",
            ),
            models.UniqueConstraint(
                fields=["tenant", "key", "number"], name="customization_rule_number_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "key"],
                condition=models.Q(status="draft"),
                name="customization_rule_one_draft",
            ),
            models.UniqueConstraint(
                fields=["tenant", "key"],
                condition=models.Q(status="published"),
                name="customization_rule_one_published",
            ),
        ]

    def __str__(self) -> str:
        return f"rule {self.key} v{self.number}"


class FieldDefinition(TenantScopedModel):
    """A custom field of a declared entity (CUSTOMIZATION_ENGINE.md §4.2). ``key`` and
    ``field_type`` never change: a field is deprecated and a new one created instead."""

    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        LONG_TEXT = "long_text", "Long text"
        NUMBER = "number", "Whole number"
        DECIMAL = "decimal", "Decimal"
        DATE = "date", "Date"
        BOOLEAN = "boolean", "Yes / no"
        SINGLE_SELECT = "single_select", "Single choice"
        MULTI_SELECT = "multi_select", "Multiple choice"
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"

    class Visibility(models.TextChoices):
        INTERNAL = "internal", "Staff only"
        PORTAL = "portal", "Portal"
        PUBLIC = "public", "Public forms"

    entity = models.CharField(max_length=80)
    key = models.CharField(max_length=64)
    field_type = models.CharField(max_length=16, choices=FieldType.choices)
    labels = models.JSONField(default=dict)  # locale -> label
    required = models.BooleanField(default=False)
    options = models.JSONField(default=list, blank=True)  # selects: [{value, labels}]
    validation = models.JSONField(default=dict, blank=True)  # min/max, min/max_length
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.INTERNAL
    )
    view_permission = models.CharField(max_length=100, blank=True, default="")
    edit_permission = models.CharField(max_length=100, blank=True, default="")
    pii = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)
    deprecated_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "customization_fielddefinition"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(key__regex=r"^[a-z][a-z0-9_]{1,63}$"),
                name="customization_field_key_valid",
            ),
            models.UniqueConstraint(
                fields=["tenant", "entity", "key"], name="customization_field_key_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.entity}.{self.key}"


class FormDefinition(TenantScopedModel):
    """A versioned form layout of a declared entity (CUSTOMIZATION_ENGINE.md §4.3): sections of
    core and custom fields, with optional visibility rules (``customization.form_visibility``)."""

    key = models.CharField(max_length=64)
    entity = models.CharField(max_length=80)
    name = models.CharField(max_length=120)
    layout = models.JSONField(default=dict)
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Lifecycle.choices, default=Lifecycle.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.UUIDField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "customization_formdefinition"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(key__regex=r"^[a-z][a-z0-9_]{1,63}$"),
                name="customization_form_key_valid",
            ),
            models.UniqueConstraint(
                fields=["tenant", "key", "number"], name="customization_form_number_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "key"],
                condition=models.Q(status="draft"),
                name="customization_form_one_draft",
            ),
            models.UniqueConstraint(
                fields=["tenant", "key"],
                condition=models.Q(status="published"),
                name="customization_form_one_published",
            ),
        ]

    def __str__(self) -> str:
        return f"form {self.key} v{self.number}"


class WorkflowDefinition(TenantScopedModel):
    """A versioned declarative state machine (CUSTOMIZATION_ENGINE.md §4.4) for a declared
    subject. Instances pin the version they started with."""

    key = models.CharField(max_length=64)
    subject = models.CharField(max_length=80)
    name = models.CharField(max_length=120)
    spec = models.JSONField(default=dict)  # states, initial, transitions, sla_hours
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Lifecycle.choices, default=Lifecycle.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.UUIDField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "customization_workflowdefinition"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(key__regex=r"^[a-z][a-z0-9_]{1,63}$"),
                name="customization_workflow_key_valid",
            ),
            models.UniqueConstraint(
                fields=["tenant", "key", "number"], name="customization_workflow_number_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "key"],
                condition=models.Q(status="draft"),
                name="customization_workflow_one_draft",
            ),
            models.UniqueConstraint(
                fields=["tenant", "key"],
                condition=models.Q(status="published"),
                name="customization_workflow_one_published",
            ),
            models.UniqueConstraint(fields=["tenant", "id"], name="customization_wfd_tenant_key"),
        ]

    def __str__(self) -> str:
        return f"workflow {self.key} v{self.number}"


class WorkflowInstance(TenantScopedModel):
    definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.PROTECT, related_name="+", db_constraint=False
    )
    subject = models.CharField(max_length=80)
    subject_id = models.UUIDField()
    state = models.CharField(max_length=40)
    context = models.JSONField(default=dict, blank=True)  # subject.* values for guards
    started_by = models.UUIDField()
    entered_state_at = models.DateTimeField()
    sla_due_at = models.DateTimeField(null=True, blank=True)
    sla_breached_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "customization_workflowinstance"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "definition", "subject_id"],
                condition=models.Q(finished_at__isnull=True),
                name="customization_workflow_one_open_per_subject",
            ),
            models.UniqueConstraint(fields=["tenant", "id"], name="customization_wfi_tenant_key"),
        ]

    def __str__(self) -> str:
        return f"workflow instance {self.pk} ({self.state})"


class WorkflowStep(TenantScopedModel):
    """Append-only history of an instance (who moved it, from where to where, why)."""

    instance = models.ForeignKey(
        WorkflowInstance, on_delete=models.PROTECT, related_name="steps", db_constraint=False
    )
    transition = models.CharField(max_length=40)
    from_state = models.CharField(max_length=40)
    to_state = models.CharField(max_length=40)
    actor = models.UUIDField()
    note = models.CharField(max_length=500, blank=True, default="")

    class Meta(TenantScopedModel.Meta):
        db_table = "customization_workflowstep"

    def __str__(self) -> str:
        return f"{self.from_state} -> {self.to_state}"


class TemplateDefinition(TenantScopedModel):
    """A versioned template of a declared kind (ADR-056); ``content`` holds one subject/body
    per locale: ``{"en": {"subject": "...", "body": "..."}, "bn": {...}}``."""

    key = models.CharField(max_length=64)
    kind = models.CharField(max_length=80)
    name = models.CharField(max_length=120)
    content = models.JSONField(default=dict)
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Lifecycle.choices, default=Lifecycle.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.UUIDField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "customization_templatedefinition"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(key__regex=r"^[a-z][a-z0-9_]{1,63}$"),
                name="customization_template_key_valid",
            ),
            models.UniqueConstraint(
                fields=["tenant", "key", "number"], name="customization_template_number_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "key"],
                condition=models.Q(status="draft"),
                name="customization_template_one_draft",
            ),
            models.UniqueConstraint(
                fields=["tenant", "key"],
                condition=models.Q(status="published"),
                name="customization_template_one_published",
            ),
        ]

    def __str__(self) -> str:
        return f"template {self.key} v{self.number}"


class NumberingSequence(TenantScopedModel):
    """A numbering pattern (CUSTOMIZATION_ENGINE.md §4.7), e.g. ``RCP-{INST}-{YYYY}-{SEQ:5}``.
    Counters are allocated gap-free under a row lock inside the business transaction."""

    class Scope(models.TextChoices):
        TENANT = "tenant", "Organisation"
        INSTITUTION = "institution", "Institution"
        CAMPUS = "campus", "Campus"

    class Reset(models.TextChoices):
        NEVER = "never", "Never"
        YEARLY = "yearly", "Every calendar year"
        ACADEMIC_YEAR = "academic_year", "Every academic year"

    key = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    pattern = models.CharField(max_length=64)
    scope = models.CharField(max_length=16, choices=Scope.choices, default=Scope.TENANT)
    reset = models.CharField(max_length=16, choices=Reset.choices, default=Reset.NEVER)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        db_table = "customization_numberingsequence"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(key__regex=r"^[a-z][a-z0-9_]{1,63}$"),
                name="customization_numbering_key_valid",
            ),
            models.UniqueConstraint(
                fields=["tenant", "key"], name="customization_numbering_key_unique"
            ),
            models.UniqueConstraint(
                fields=["tenant", "id"], name="customization_numbering_tenant_key"
            ),
        ]

    def __str__(self) -> str:
        return f"sequence {self.key}"


class NumberCounter(TenantScopedModel):
    sequence = models.ForeignKey(
        NumberingSequence, on_delete=models.PROTECT, related_name="+", db_constraint=False
    )
    institution_id = models.UUIDField(null=True, blank=True)
    campus_id = models.UUIDField(null=True, blank=True)
    period = models.CharField(max_length=16, blank=True, default="")
    value = models.PositiveBigIntegerField(default=0)

    class Meta(TenantScopedModel.Meta):
        db_table = "customization_numbercounter"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "sequence", "institution_id", "campus_id", "period"],
                nulls_distinct=False,
                name="customization_counter_unique",
            )
        ]

    def __str__(self) -> str:
        return f"counter {self.sequence_id} {self.period} = {self.value}"
