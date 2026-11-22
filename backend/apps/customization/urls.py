"""Customization Studio routes (Phase 5 M6)."""

from django.urls import path

from apps.customization.api import views as v

app_name = "customization"

urlpatterns = [
    path("customization/catalog/", v.CatalogView.as_view(), name="catalog"),
    path("customization/config/", v.ConfigView.as_view(), name="config"),
    path("customization/config/publish/", v.ConfigPublishView.as_view(), name="config-publish"),
    path("customization/config/rollback/", v.ConfigRollbackView.as_view(), name="config-rollback"),
    path("customization/fields/", v.FieldsView.as_view(), name="fields"),
    path("customization/fields/<str:field_id>/", v.FieldDetailView.as_view(), name="field"),
    path(
        "customization/fields/<str:field_id>/deprecate/",
        v.FieldDeprecateView.as_view(),
        name="field-deprecate",
    ),
    path("customization/rules/", v.RulesView.as_view(), name="rules"),
    path("customization/rules/test/", v.RuleTestView.as_view(), name="rule-test"),
    path(
        "customization/rules/<str:key>/publish/", v.RulePublishView.as_view(), name="rule-publish"
    ),
    path("customization/forms/", v.FormsView.as_view(), name="forms"),
    path(
        "customization/forms/<str:key>/publish/", v.FormPublishView.as_view(), name="form-publish"
    ),
    path("customization/forms/<str:key>/render/", v.FormRenderView.as_view(), name="form-render"),
    path(
        "customization/forms/<str:key>/visibility/",
        v.FormVisibilityView.as_view(),
        name="form-visibility",
    ),
    path(
        "customization/forms/<str:key>/validate/",
        v.FormValidateView.as_view(),
        name="form-validate",
    ),
    path("customization/workflows/", v.WorkflowsView.as_view(), name="workflows"),
    path(
        "customization/workflows/<str:key>/publish/",
        v.WorkflowPublishView.as_view(),
        name="workflow-publish",
    ),
    path(
        "customization/workflows/<str:key>/start/",
        v.WorkflowStartView.as_view(),
        name="workflow-start",
    ),
    path(
        "customization/workflow-requests/<str:instance_id>/",
        v.WorkflowRequestView.as_view(),
        name="workflow-request",
    ),
    path(
        "customization/workflow-requests/<str:instance_id>/transition/",
        v.WorkflowTransitionView.as_view(),
        name="workflow-transition",
    ),
    path("customization/templates/", v.TemplatesView.as_view(), name="templates"),
    path(
        "customization/templates/preview/", v.TemplatePreviewView.as_view(), name="template-preview"
    ),
    path(
        "customization/templates/<str:key>/publish/",
        v.TemplatePublishView.as_view(),
        name="template-publish",
    ),
    path("customization/numbering/", v.SequencesView.as_view(), name="numbering"),
    path("platform/presets/", v.PlatformPresetsView.as_view(), name="platform-presets"),
]
