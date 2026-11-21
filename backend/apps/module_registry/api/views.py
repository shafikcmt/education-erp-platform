"""Module registry API (Phase 4 M5; plan §6): the module catalogue (read-only) and feature
flags (data-only rollout controls, ADR-053). Platform host only; writes run P17 inside the
service with the permission checked again, uncached."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from apps.identity.api.utils import CsrfProtectedView, service_errors
from apps.identity.models import User
from apps.module_registry import services
from apps.module_registry.models import FeatureFlag, Module
from apps.rbac.permissions import HasPermission

TAGS = ["platform-modules"]


class ModuleSerializer(serializers.Serializer[Any]):
    code = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()
    version = serializers.CharField()
    dependencies = serializers.ListField(child=serializers.CharField())
    sellable = serializers.BooleanField()
    available = serializers.BooleanField()


class FlagSerializer(serializers.Serializer[Any]):
    key = serializers.RegexField(r"^[a-z][a-z0-9_.]{2,79}$")
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    default_enabled = serializers.BooleanField()
    rules = serializers.DictField(required=False)


class ModulesView(CsrfProtectedView):
    permission_classes = [HasPermission({"GET": "module_registry.module.view"})]
    platform_operations = {"GET": "P17"}

    @extend_schema(tags=TAGS, summary="Module catalogue", responses=ModuleSerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = Module.objects.filter(deprecated_at__isnull=True).order_by("category", "code")
        return Response(ModuleSerializer(rows, many=True).data)


class FeatureFlagsView(CsrfProtectedView):
    permission_classes = [
        HasPermission({"GET": "module_registry.module.view", "POST": "module_registry.flag.manage"})
    ]
    platform_operations = {"GET": "P17", "POST": "P17"}

    @extend_schema(tags=TAGS, summary="Feature flags", responses=FlagSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(FlagSerializer(FeatureFlag.objects.order_by("key"), many=True).data)

    @extend_schema(
        tags=TAGS,
        summary="Create or update a feature flag (default, percentage, plans, tenants)",
        request=FlagSerializer,
        responses=FlagSerializer,
    )
    def post(self, request: Request) -> Response:
        data = FlagSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        assert isinstance(request.user, User)  # noqa: S101 - permission classes guarantee it
        with service_errors():
            flag = services.set_flag(
                actor=request.user,
                key=values["key"],
                default_enabled=values["default_enabled"],
                rules=values.get("rules") or {},
                description=values.get("description", ""),
                request=request,
            )
        return Response(FlagSerializer(flag).data)
