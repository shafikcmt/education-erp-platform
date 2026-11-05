"""S3 compatibility and bucket-isolation checks against a REAL object store (ADR-029).

Opt-in: runs only with ``S3_INTEGRATION=1`` (CI ``e2e-smoke`` job and ``make s3-check``), using
the app's own credentials from the environment. Covers every S3 feature the platform relies on.
Set ``S3_ISOLATION_PROBE_BUCKET`` to an existing bucket the app must NOT be able to access.
"""

import hashlib
import io
import os
import time
import urllib.error
import urllib.request

import boto3
import pytest
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError
from storages.backends.s3 import S3Storage

from apps.core.ids import new_id

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("S3_INTEGRATION") != "1", reason="set S3_INTEGRATION=1"),
]

ENDPOINT = os.environ.get("S3_ENDPOINT_URL", "")
BUCKET = os.environ.get("S3_BUCKET", "")


def _client(access_key=None, secret_key=None):
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=access_key or os.environ.get("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=secret_key or os.environ.get("S3_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@pytest.fixture
def s3():
    return _client()


@pytest.fixture
def prefix(s3):
    value = f"_integration/{new_id()}/"
    yield value
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=value):
        for item in page.get("Contents", []):
            s3.delete_object(Bucket=BUCKET, Key=item["Key"])


def _error_code(excinfo) -> str:
    return str(excinfo.value.response["Error"]["Code"])


# ----------------------------------------------------------------- compatibility
def test_django_storages_backend_round_trip(prefix):
    storage = S3Storage(
        bucket_name=BUCKET,
        endpoint_url=ENDPOINT,
        access_key=os.environ["S3_ACCESS_KEY_ID"],
        secret_key=os.environ["S3_SECRET_ACCESS_KEY"],
        addressing_style="path",
        signature_version="s3v4",
        default_acl=None,
        file_overwrite=False,
    )
    name = storage.save(f"{prefix}report.pdf", io.BytesIO(b"%PDF-1.7 report"))
    assert storage.exists(name)
    assert storage.size(name) == len(b"%PDF-1.7 report")
    with storage.open(name) as handle:
        assert handle.read() == b"%PDF-1.7 report"
    second = storage.save(f"{prefix}report.pdf", io.BytesIO(b"other"))
    assert second != name, "file_overwrite=False must never replace an existing object"
    storage.delete(name)
    assert not storage.exists(name)


def test_put_get_head_metadata_and_range(s3, prefix):
    key = f"{prefix}data.bin"
    body = bytes(range(256)) * 16
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body,
        ContentType="application/x-test",
        Metadata={"origin": "integration"},
    )
    head = s3.head_object(Bucket=BUCKET, Key=key)
    assert head["ContentLength"] == len(body)
    assert head["ContentType"] == "application/x-test"
    assert head["Metadata"]["origin"] == "integration"
    ranged = s3.get_object(Bucket=BUCKET, Key=key, Range="bytes=10-19")["Body"].read()
    assert ranged == body[10:20]


def test_multipart_upload_integrity(s3, prefix):
    key = f"{prefix}large.bin"
    payload = os.urandom(12 * 1024 * 1024)  # 12 MiB -> multipart with 5 MiB parts
    config = TransferConfig(
        multipart_threshold=5 * 1024 * 1024, multipart_chunksize=5 * 1024 * 1024
    )
    s3.upload_fileobj(io.BytesIO(payload), BUCKET, key, Config=config)
    etag = s3.head_object(Bucket=BUCKET, Key=key)["ETag"]
    assert "-" in etag, f"expected a multipart ETag, got {etag}"
    downloaded = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    assert hashlib.sha256(downloaded).digest() == hashlib.sha256(payload).digest()


def test_copy_and_paginated_listing(s3, prefix):
    for i in range(5):
        s3.put_object(Bucket=BUCKET, Key=f"{prefix}list/{i}.txt", Body=f"{i}".encode())
    s3.copy_object(
        Bucket=BUCKET,
        Key=f"{prefix}copy.txt",
        CopySource={"Bucket": BUCKET, "Key": f"{prefix}list/3.txt"},
    )
    assert s3.get_object(Bucket=BUCKET, Key=f"{prefix}copy.txt")["Body"].read() == b"3"
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=BUCKET, Prefix=f"{prefix}list/", PaginationConfig={"PageSize": 2}
    ):
        keys += [item["Key"] for item in page.get("Contents", [])]
    assert keys == [f"{prefix}list/{i}.txt" for i in range(5)]


def test_presigned_url_works_then_expires_and_rejects_tampering(s3, prefix):
    key = f"{prefix}private.txt"
    s3.put_object(Bucket=BUCKET, Key=key, Body=b"secret-content")
    url = s3.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=2
    )
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - test endpoint
        assert response.read() == b"secret-content"
    # Well-formed but wrong signature (same length, one hex digit flipped) -> must be 403.
    signature = url.split("X-Amz-Signature=")[1].split("&")[0]
    flipped = signature[:-1] + ("0" if signature[-1] != "0" else "1")
    tampered = url.replace(f"X-Amz-Signature={signature}", f"X-Amz-Signature={flipped}")
    with pytest.raises(urllib.error.HTTPError) as denied:
        urllib.request.urlopen(tampered, timeout=5)  # noqa: S310
    assert denied.value.code == 403
    time.sleep(3)
    with pytest.raises(urllib.error.HTTPError) as expired:
        urllib.request.urlopen(url, timeout=5)  # noqa: S310
    assert expired.value.code == 403


# ----------------------------------------------------------------- isolation
def test_anonymous_access_is_denied(s3, prefix):
    key = f"{prefix}private.txt"
    s3.put_object(Bucket=BUCKET, Key=key, Body=b"secret")
    for url in (f"{ENDPOINT}/{BUCKET}/{key}", f"{ENDPOINT}/{BUCKET}?list-type=2"):
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(url, timeout=5)  # noqa: S310
        assert denied.value.code == 403


def test_wrong_secret_is_rejected():
    with pytest.raises(ClientError) as denied:
        _client(secret_key="wrong-secret-key").list_objects_v2(Bucket=BUCKET, MaxKeys=1)
    assert _error_code(denied) in {"SignatureDoesNotMatch", "AccessDenied", "InvalidAccessKeyId"}


def test_app_identity_cannot_create_buckets(s3):
    with pytest.raises(ClientError) as denied:
        s3.create_bucket(Bucket=f"erp-rogue-{new_id().hex[:12]}")
    assert _error_code(denied) == "AccessDenied"


@pytest.mark.skipif(
    not os.environ.get("S3_ISOLATION_PROBE_BUCKET"),
    reason="set S3_ISOLATION_PROBE_BUCKET to an existing foreign bucket",
)
def test_app_identity_cannot_touch_a_foreign_bucket(s3):
    foreign = os.environ["S3_ISOLATION_PROBE_BUCKET"]
    for call in (
        lambda: s3.list_objects_v2(Bucket=foreign, MaxKeys=1),
        lambda: s3.put_object(Bucket=foreign, Key="x.txt", Body=b"x"),
        lambda: s3.get_object(Bucket=foreign, Key="x.txt"),
        lambda: s3.delete_bucket(Bucket=foreign),
    ):
        with pytest.raises(ClientError) as denied:
            call()
        assert _error_code(denied) == "AccessDenied"
