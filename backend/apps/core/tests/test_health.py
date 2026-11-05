import pytest

from apps.core import health

pytestmark = pytest.mark.django_db


def test_liveness(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_ok_when_all_dependencies_up(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "cache": "ok", "storage": "ok"},
    }


@pytest.mark.parametrize("failing", ["database", "cache", "storage"])
def test_readiness_503_problem_details_when_a_dependency_fails(client, monkeypatch, failing):
    def boom():
        raise ConnectionError("internal-hostname:5432 refused")  # must not leak

    monkeypatch.setitem(health.READINESS_CHECKS, failing, boom)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response["Content-Type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "service_unavailable"
    assert body["checks"][failing] == "fail"
    assert "internal-hostname" not in response.content.decode()


def test_system_health_api_endpoint(client):
    response = client.get("/api/v1/system/health/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "version", "environment"}


def test_system_health_reports_degraded(client, monkeypatch):
    monkeypatch.setitem(health.READINESS_CHECKS, "cache", lambda: False)
    assert client.get("/api/v1/system/health/").json()["status"] == "degraded"


def test_storage_check_uses_head_bucket_for_s3_backends(monkeypatch):
    calls = {}

    class _Client:
        def head_bucket(self, Bucket):  # noqa: N803 - boto3 signature
            calls["bucket"] = Bucket

    class _Meta:
        client = _Client()

    class _Conn:
        meta = _Meta()

    class _Storage:
        connection = _Conn()
        bucket_name = "erp-test-bucket"

    monkeypatch.setattr(health, "default_storage", _Storage())
    assert health.check_storage() is True
    assert calls == {"bucket": "erp-test-bucket"}
