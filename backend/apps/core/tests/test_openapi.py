import pytest
from drf_spectacular.drainage import GENERATOR_STATS
from drf_spectacular.generators import SchemaGenerator


@pytest.fixture
def schema():
    GENERATOR_STATS.reset()
    generated = SchemaGenerator().get_schema(request=None, public=True)
    return generated


def test_schema_generates_without_warnings_or_errors(schema):
    assert not GENERATOR_STATS._warn_cache, f"warnings: {list(GENERATOR_STATS._warn_cache)}"
    assert not GENERATOR_STATS._error_cache, f"errors: {list(GENERATOR_STATS._error_cache)}"


def test_schema_contains_versioned_api_and_excludes_probes(schema):
    assert "/api/v1/system/health/" in schema["paths"]
    assert "/healthz" not in schema["paths"]
    assert "/readyz" not in schema["paths"]
    assert schema["info"]["title"] == "Education ERP API"
