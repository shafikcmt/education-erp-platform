"""Object storage operations for files (Phase 6 M3; ADR-064).

* Presigning (``presigned_post``, ``presigned_get``) is local signing, no network: allowed
  anywhere. URLs are signed for ``S3_PUBLIC_ENDPOINT_URL`` (what browsers reach).
* ``head`` and ``delete`` are network I/O: refused inside an open tenant transaction (they run in
  tasks, ``assert_no_open_tenant_transaction``).
"""

from __future__ import annotations

from functools import cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings

from apps.core.tenancy.keys import assert_no_open_tenant_transaction

UPLOAD_SECONDS = 600
DOWNLOAD_SECONDS = 300


def _options() -> dict[str, Any]:
    return dict(settings.S3_CONNECTION)


def _client(endpoint: str) -> Any:
    options = _options()
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=options["access_key"],
        aws_secret_access_key=options["secret_key"],
        region_name=options.get("region_name", "us-east-1"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@cache
def _public() -> Any:
    return _client(getattr(settings, "S3_PUBLIC_ENDPOINT_URL", "") or _options()["endpoint_url"])


@cache
def _internal() -> Any:
    return _client(_options()["endpoint_url"])


def presigned_post(key: str, content_type: str, max_bytes: int) -> dict[str, Any]:
    """A POST form bound to this key, this content type and at most ``max_bytes``."""
    result: dict[str, Any] = _public().generate_presigned_post(
        Bucket=_options()["bucket_name"],
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, max_bytes]],
        ExpiresIn=UPLOAD_SECONDS,
    )
    return result


def presigned_get(key: str, filename: str) -> str:
    """A short-lived download link that always downloads (never renders inline)."""
    safe = "".join(c for c in filename if c.isalnum() or c in "._- ")[:100] or "file"
    url: str = _public().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": _options()["bucket_name"],
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{safe}"',
        },
        ExpiresIn=DOWNLOAD_SECONDS,
    )
    return url


def head(key: str) -> dict[str, Any] | None:
    assert_no_open_tenant_transaction("Storage access")
    try:
        response: dict[str, Any] = _internal().head_object(
            Bucket=_options()["bucket_name"], Key=key
        )
    except ClientError:
        return None
    return {"size": int(response["ContentLength"]), "content_type": response.get("ContentType", "")}


def delete(key: str) -> None:
    assert_no_open_tenant_transaction("Storage access")
    _internal().delete_object(Bucket=_options()["bucket_name"], Key=key)
