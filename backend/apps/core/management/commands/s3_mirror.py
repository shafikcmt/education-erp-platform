"""Provider-agnostic object-storage backup, restore and migration (ADR-029 portability).

Copies every object between any two *locations*, verifying each copy by SHA-256:

* the application bucket (``S3_*`` settings, the default source),
* another S3-compatible bucket (``--to-endpoint``/``--from-endpoint`` + credentials read from
  the environment variables you name — credentials are never passed on the command line),
* a local directory (writes/reads ``manifest.json`` with sizes, content types and hashes).

Examples::

    manage.py s3_mirror --to-dir /backups/objects-2026-11-05        # backup
    manage.py s3_mirror --from-dir /backups/objects-2026-11-05      # restore into app bucket
    manage.py s3_mirror --to-endpoint https://s3.other.example --to-bucket erp \\
        --to-access-key-env OTHER_KEY --to-secret-key-env OTHER_SECRET          # migrate provider

Production backup policy (schedule, retention, off-site target) is decided in Phase 19.
"""

import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import boto3
from botocore.config import Config
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

MANIFEST = "manifest.json"


@dataclass(frozen=True)
class StoredObject:
    key: str
    body: bytes
    content_type: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


class Location(Protocol):
    def iter_keys(self) -> Iterator[str]: ...
    def read(self, key: str) -> StoredObject: ...
    def write(self, obj: StoredObject) -> None: ...
    def finish(self) -> None: ...


class S3Location:
    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        self.bucket = bucket
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def iter_keys(self) -> Iterator[str]:
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket):
            for item in page.get("Contents", []):
                yield str(item["Key"])

    def read(self, key: str) -> StoredObject:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return StoredObject(
            key=key,
            body=response["Body"].read(),
            content_type=response.get("ContentType") or "application/octet-stream",
        )

    def write(self, obj: StoredObject) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=obj.key, Body=obj.body, ContentType=obj.content_type
        )

    def finish(self) -> None:
        return None


class DirLocation:
    """Directory backup format: one file per object + ``manifest.json``."""

    def __init__(self, root: Path, *, create: bool) -> None:
        self.root = root
        if create:
            root.mkdir(parents=True, exist_ok=True)
            if any(root.iterdir()):
                raise CommandError(f"backup directory {root} must be empty")
            self.manifest: dict[str, dict[str, Any]] = {}
        else:
            manifest_path = root / MANIFEST
            if not manifest_path.is_file():
                raise CommandError(f"{manifest_path} not found — not a backup directory")
            self.manifest = json.loads(manifest_path.read_text())

    def _path(self, key: str) -> Path:
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise CommandError(f"refusing unsafe object key {key!r}")
        return self.root / "objects" / Path(*relative.parts)

    def iter_keys(self) -> Iterator[str]:
        yield from sorted(self.manifest)

    def read(self, key: str) -> StoredObject:
        entry = self.manifest[key]
        obj = StoredObject(
            key=key, body=self._path(key).read_bytes(), content_type=entry["content_type"]
        )
        if obj.sha256 != entry["sha256"]:
            raise CommandError(f"backup file for {key!r} is corrupt (sha256 mismatch)")
        return obj

    def write(self, obj: StoredObject) -> None:
        path = self._path(obj.key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(obj.body)
        self.manifest[obj.key] = {
            "sha256": obj.sha256,
            "size": len(obj.body),
            "content_type": obj.content_type,
        }

    def finish(self) -> None:
        (self.root / MANIFEST).write_text(json.dumps(self.manifest, indent=2, sort_keys=True))


def mirror(source: Location, target: Location) -> dict[str, Any]:
    """Copy all objects; re-read each copy from the target and compare SHA-256."""
    copied, total_bytes = 0, 0
    for key in source.iter_keys():
        obj = source.read(key)
        target.write(obj)
        copied_back = target.read(key) if not isinstance(target, DirLocation) else obj
        if copied_back.sha256 != obj.sha256:
            raise CommandError(f"verification failed for {key!r}")
        copied += 1
        total_bytes += len(obj.body)
    target.finish()
    return {"objects": copied, "bytes": total_bytes, "verified": True}


def app_bucket() -> S3Location:
    options = settings.STORAGES["default"].get("OPTIONS", {})
    if "endpoint_url" not in options:
        raise CommandError("the default storage is not S3-compatible in these settings")
    return S3Location(
        endpoint=options["endpoint_url"],
        bucket=options["bucket_name"],
        access_key=options["access_key"],
        secret_key=options["secret_key"],
        region=options.get("region_name", "us-east-1"),
    )


def _env(name: str | None, flag: str) -> str:
    if not name:
        raise CommandError(f"{flag} is required with an S3 endpoint")
    value = os.environ.get(name)
    if not value:
        raise CommandError(f"environment variable {name} (from {flag}) is not set")
    return value


class Command(BaseCommand):
    help = "Backup, restore or migrate object storage between S3-compatible providers/directories."

    def add_arguments(self, parser: CommandParser) -> None:
        source = parser.add_mutually_exclusive_group()
        source.add_argument("--from-dir", type=Path, help="restore from a backup directory")
        source.add_argument("--from-endpoint", help="source S3 endpoint (default: app bucket)")
        parser.add_argument("--from-bucket")
        parser.add_argument("--from-access-key-env")
        parser.add_argument("--from-secret-key-env")
        target = parser.add_mutually_exclusive_group()
        target.add_argument("--to-dir", type=Path, help="write a backup directory")
        target.add_argument("--to-endpoint", help="target S3 endpoint (default: app bucket)")
        parser.add_argument("--to-bucket")
        parser.add_argument("--to-access-key-env")
        parser.add_argument("--to-secret-key-env")

    def handle(self, *args: Any, **opts: Any) -> None:
        source: Location
        target: Location
        if opts["from_dir"]:
            source = DirLocation(opts["from_dir"], create=False)
        elif opts["from_endpoint"]:
            source = S3Location(
                endpoint=opts["from_endpoint"],
                bucket=opts["from_bucket"] or "",
                access_key=_env(opts["from_access_key_env"], "--from-access-key-env"),
                secret_key=_env(opts["from_secret_key_env"], "--from-secret-key-env"),
            )
        else:
            source = app_bucket()

        if opts["to_dir"]:
            target = DirLocation(opts["to_dir"], create=True)
        elif opts["to_endpoint"]:
            target = S3Location(
                endpoint=opts["to_endpoint"],
                bucket=opts["to_bucket"] or "",
                access_key=_env(opts["to_access_key_env"], "--to-access-key-env"),
                secret_key=_env(opts["to_secret_key_env"], "--to-secret-key-env"),
            )
        else:
            target = app_bucket()

        if not (opts["from_dir"] or opts["from_endpoint"] or opts["to_dir"] or opts["to_endpoint"]):
            raise CommandError("nothing to do: give a --from-* or --to-* location")
        report = mirror(source, target)
        self.stdout.write(json.dumps(report))
