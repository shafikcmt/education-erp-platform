"""Public admissions API on tenant hosts (Phase 6 M5; ADR-065).

Anonymous by design (reviewed allow-list): throttled, enumeration-safe, honeypot, single-use
hashed tokens in the URL fragment. Answers 404 when the organisation has no ``admissions``
module (anonymous callers learn nothing else). Tokens are sent in the request body, never in
the URL.
"""

from __future__ import annotations

from typing import Any

from django.utils import translation
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.admissions import public
from apps.identity.api.serializers import AcceptedSerializer, TokenSerializer
from apps.identity.api.utils import service_errors
from apps.module_registry.entitlements import is_entitled
from apps.tenancy.api.views_tenant import TenantView

TAGS = ["admissions-public"]
_ACCEPTED = {"detail": "If the details are valid, a confirmation email is on its way."}


class PublicTargetSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    unit = serializers.CharField()
    unit_name = serializers.CharField()


class PublicCycleSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    name_i18n = serializers.DictField(child=serializers.CharField())
    closes_on = serializers.DateField()
    fee_amount = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    fee_currency = serializers.CharField()
    targets = PublicTargetSerializer(many=True)


class PublicSubmitSerializer(serializers.Serializer[Any]):
    target = serializers.UUIDField()
    values = serializers.DictField()
    # Honeypot: hidden from people, filled by bots. Any value makes the request a silent no-op.
    website = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class StatusDocumentSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    status = serializers.CharField()


class StatusTestSerializer(serializers.Serializer[Any]):
    name = serializers.CharField()
    starts_at = serializers.DateTimeField()
    venue = serializers.CharField()
    seat = serializers.IntegerField()


class PublicStatusSerializer(serializers.Serializer[Any]):
    number = serializers.CharField()
    status = serializers.CharField()
    cycle = serializers.CharField()
    applicant_name = serializers.CharField()
    decision_note = serializers.CharField()
    can_add_documents = serializers.BooleanField()
    documents = StatusDocumentSerializer(many=True)
    tests = StatusTestSerializer(many=True)


class RespondSerializer(TokenSerializer):
    accept = serializers.BooleanField()


class DocumentSlotRequestSerializer(TokenSerializer):
    name = serializers.CharField(max_length=200)
    size = serializers.IntegerField(min_value=1)
    content_type = serializers.CharField(max_length=100)


class DocumentSlotSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    url = serializers.URLField()
    fields = serializers.DictField(child=serializers.CharField())  # type: ignore[assignment]  # field name shadows a DRF attribute


class DocumentConfirmSerializer(TokenSerializer):
    file = serializers.UUIDField()


class PublicView(TenantView):
    permission_classes = [AllowAny]
    tenant_auth_flow = True  # applicants are not members
    module_code = "admissions"

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if not is_entitled("admissions"):
            raise NotFound()  # the organisation doesn't take applications here


def _locale() -> str:
    return translation.get_language() or "en"


class OpenCyclesView(PublicView):
    @extend_schema(tags=TAGS, summary="Open admissions", responses=PublicCycleSerializer(many=True))
    def get(self, request: Request) -> Response:
        from apps.academics.models import Unit

        cycles = public.open_cycles()
        units = {
            u.pk: u
            for u in Unit.objects.filter(
                pk__in=[t.unit_id for c in cycles for t in c.targets.all()]
            )
        }
        data = [
            {
                "id": c.pk,
                "name": c.name,
                "name_i18n": c.name_i18n,
                "closes_on": c.closes_on,
                "fee_amount": c.fee_amount,
                "fee_currency": c.fee_currency,
                "targets": [
                    {
                        "id": t.pk,
                        "unit": units[t.unit_id].level_key,
                        "unit_name": units[t.unit_id].name,
                    }
                    for t in c.targets.all()
                ],
            }
            for c in cycles
        ]
        return Response(PublicCycleSerializer(data, many=True).data)


class CycleFormView(PublicView):
    @extend_schema(tags=TAGS, summary="The application form of an open cycle", responses=dict)
    def get(self, request: Request, cycle_id: str) -> Response:
        from apps.customization.forms import render

        with service_errors():
            cycle = public.open_cycle(cycle_id)
            return Response(render(cycle.form_key))


class CycleVisibilityView(PublicView):
    @extend_schema(
        tags=TAGS,
        summary="Sections visible for these values",
        request=PublicSubmitSerializer,
        responses=dict,
    )
    def post(self, request: Request, cycle_id: str) -> Response:
        from apps.customization.forms import visible_sections

        values = request.data.get("values") if isinstance(request.data, dict) else None
        with service_errors():
            cycle = public.open_cycle(cycle_id)
            shown = visible_sections(cycle.form_key, values if isinstance(values, dict) else {})
        return Response({"sections": shown})


class SubmitView(PublicView):
    @extend_schema(
        tags=TAGS,
        summary="Apply (an email confirmation follows)",
        request=PublicSubmitSerializer,
        responses={202: AcceptedSerializer},
    )
    def post(self, request: Request, cycle_id: str) -> Response:
        form = PublicSubmitSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        with service_errors():
            public.submit_public(
                request._request, cycle_id=cycle_id, locale=_locale(), **form.validated_data
            )
        return Response(_ACCEPTED, status=status.HTTP_202_ACCEPTED)


class VerifyView(PublicView):
    @extend_schema(
        tags=TAGS, summary="Confirm an application", request=TokenSerializer,
        responses=AcceptedSerializer,
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        form = TokenSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        with service_errors():
            public.verify_public(request._request, form.validated_data["token"], locale=_locale())
        return Response({"detail": "Submitted. A personal status link is on its way."})


class StatusView(PublicView):
    @extend_schema(
        tags=TAGS, summary="My application (status link)", request=TokenSerializer,
        responses=PublicStatusSerializer,
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        form = TokenSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        with service_errors():
            data = public.status_of(form.validated_data["token"])
        return Response(PublicStatusSerializer(data).data)


class RespondView(PublicView):
    @extend_schema(
        tags=TAGS, summary="Answer an offer", request=RespondSerializer,
        responses=PublicStatusSerializer,
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        form = RespondSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        token = form.validated_data["token"]
        with service_errors():
            public.respond_public(request._request, token, accept=form.validated_data["accept"])
            data = public.status_of(token)
        return Response(PublicStatusSerializer(data).data)


class DocumentSlotView(PublicView):
    @extend_schema(
        tags=TAGS, summary="Ask for a document upload slot", request=DocumentSlotRequestSerializer,
        responses={201: DocumentSlotSerializer},
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        form = DocumentSlotRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        v = dict(form.validated_data)
        token = v.pop("token")
        with service_errors():
            row, post = public.document_slot(request._request, token, **v)
        data = {"id": row.pk, "url": post["url"], "fields": post["fields"]}
        return Response(DocumentSlotSerializer(data).data, status=status.HTTP_201_CREATED)


class DocumentConfirmView(PublicView):
    @extend_schema(
        tags=TAGS, summary="Confirm an uploaded document", request=DocumentConfirmSerializer,
        responses=PublicStatusSerializer,
    )  # fmt: skip
    def post(self, request: Request) -> Response:
        form = DocumentConfirmSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        token = form.validated_data["token"]
        with service_errors():
            public.confirm_document(request._request, token, form.validated_data["file"])
            data = public.status_of(token)
        return Response(PublicStatusSerializer(data).data)
