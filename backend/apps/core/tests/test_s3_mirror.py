import json
from collections.abc import Iterator

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.management.commands.s3_mirror import DirLocation, StoredObject, mirror


class FakeBucket:
    """In-memory stand-in for an S3 bucket (same interface as S3Location)."""

    def __init__(self, objects: dict[str, StoredObject] | None = None) -> None:
        self.objects = dict(objects or {})

    def iter_keys(self) -> Iterator[str]:
        yield from sorted(self.objects)

    def read(self, key: str) -> StoredObject:
        return self.objects[key]

    def write(self, obj: StoredObject) -> None:
        self.objects[obj.key] = obj

    def finish(self) -> None:
        return None


@pytest.fixture
def source():
    return FakeBucket(
        {
            "tenants/a/doc.pdf": StoredObject(
                "tenants/a/doc.pdf", b"%PDF-1.7 a", "application/pdf"
            ),
            "tenants/b/img.png": StoredObject("tenants/b/img.png", b"\x89PNG b", "image/png"),
            "readme.txt": StoredObject("readme.txt", "বাংলা text".encode(), "text/plain"),
        }
    )


def test_backup_to_directory_and_restore_round_trip(tmp_path, source):
    backup_dir = tmp_path / "backup"
    report = mirror(source, DirLocation(backup_dir, create=True))
    assert report == {
        "objects": 3,
        "bytes": sum(len(o.body) for o in source.objects.values()),
        "verified": True,
    }
    manifest = json.loads((backup_dir / "manifest.json").read_text())
    assert manifest["tenants/a/doc.pdf"]["content_type"] == "application/pdf"

    restored = FakeBucket()
    mirror(DirLocation(backup_dir, create=False), restored)
    assert restored.objects == source.objects


def test_bucket_to_bucket_migration_preserves_content_and_type(source):
    other_provider = FakeBucket()
    assert mirror(source, other_provider)["objects"] == 3
    assert other_provider.objects == source.objects


def test_corrupted_backup_is_detected(tmp_path, source):
    backup_dir = tmp_path / "backup"
    mirror(source, DirLocation(backup_dir, create=True))
    (backup_dir / "objects" / "readme.txt").write_bytes(b"tampered")
    with pytest.raises(CommandError, match="corrupt"):
        mirror(DirLocation(backup_dir, create=False), FakeBucket())


def test_verification_failure_is_reported(source):
    class LossyBucket(FakeBucket):
        def write(self, obj):
            super().write(StoredObject(obj.key, obj.body + b"!", obj.content_type))

    with pytest.raises(CommandError, match="verification failed"):
        mirror(source, LossyBucket())


@pytest.mark.parametrize("key", ["../escape.txt", "/etc/passwd", "a/../../b"])
def test_unsafe_keys_are_refused(tmp_path, key):
    bucket = FakeBucket({key: StoredObject(key, b"x", "text/plain")})
    with pytest.raises(CommandError, match="unsafe object key"):
        mirror(bucket, DirLocation(tmp_path / "b", create=True))


def test_refuses_non_empty_backup_dir_and_missing_manifest(tmp_path):
    (tmp_path / "existing").write_text("x")
    with pytest.raises(CommandError, match="must be empty"):
        DirLocation(tmp_path, create=True)
    with pytest.raises(CommandError, match="not a backup directory"):
        DirLocation(tmp_path / "nothing", create=False)


def test_command_requires_an_operation_and_credential_env_vars(monkeypatch, tmp_path):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    # test settings use in-memory storage, so the app bucket is not S3 here
    with pytest.raises(CommandError, match="not S3-compatible"):
        call_command("s3_mirror")
    with pytest.raises(CommandError, match="MISSING_KEY"):
        call_command(
            "s3_mirror",
            "--from-endpoint",
            "http://s3.invalid",
            "--from-bucket",
            "b",
            "--from-access-key-env",
            "MISSING_KEY",
            "--from-secret-key-env",
            "MISSING_KEY",
            "--to-dir",
            str(tmp_path / "unused-backup-dir"),
        )
