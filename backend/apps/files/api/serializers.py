"""Files API serializers (Phase 6 M3)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.files.models import StoredFile


class StoredFileSerializer(serializers.ModelSerializer[StoredFile]):
    class Meta:
        model = StoredFile
        fields = [
            "id", "purpose", "original_name", "content_type", "declared_size", "size", "status",
            "scan_state", "created_at", "verified_at",
        ]  # fmt: skip
        read_only_fields = fields


class UploadRequestSerializer(serializers.Serializer[Any]):
    purpose = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=200)
    size = serializers.IntegerField(min_value=1)
    content_type = serializers.CharField(max_length=100)


class UploadSlotSerializer(serializers.Serializer[Any]):
    file = StoredFileSerializer()
    url = serializers.URLField()
    fields = serializers.DictField(child=serializers.CharField())  # type: ignore[assignment]  # field name shadows a DRF attribute


class DownloadSerializer(serializers.Serializer[Any]):
    url = serializers.URLField()
    scan_state = serializers.CharField()
    expires_in = serializers.IntegerField()
