import uuid

from apps.core.ids import new_id


def test_new_id_returns_stdlib_uuid_version_7():
    value = new_id()
    assert type(value) is uuid.UUID
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_new_id_is_unique_and_time_ordered():
    ids = [new_id() for _ in range(10_000)]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids), "UUIDv7 values generated in one process must be monotonic"
