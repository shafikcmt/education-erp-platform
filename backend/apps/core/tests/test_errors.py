import pytest
from django.urls import path
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from config.urls import urlpatterns as root_urlpatterns

pytestmark = pytest.mark.django_db


class _Input(serializers.Serializer):
    name = serializers.CharField(max_length=5)
    age = serializers.IntegerField(min_value=0)


class _ValidateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        _Input(data=request.data).is_valid(raise_exception=True)
        return Response({"ok": True})


class _BoomView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        raise RuntimeError("database password is hunter2")  # must never leak


class _ProtectedView(APIView):
    def get(self, request):
        return Response({"secret": True})


# Test routes first: the root URLconf ends with the /api/ catch-all 404.
urlpatterns = [
    path("api/v1/_test/validate/", _ValidateView.as_view()),
    path("api/v1/_test/boom/", _BoomView.as_view()),
    path("api/v1/_test/protected/", _ProtectedView.as_view()),
    *root_urlpatterns,
]


def _assert_problem(response, status, code):
    assert response.status_code == status
    assert response["Content-Type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"].endswith(code)
    assert body["request_id"] == response["X-Request-ID"]
    return body


@pytest.mark.urls(__name__)
def test_validation_error_is_problem_details_with_field_errors(client):
    response = client.post(
        "/api/v1/_test/validate/", {"name": "toolong", "age": -1}, content_type="application/json"
    )
    body = _assert_problem(response, 400, "validation_error")
    fields = {e["field"]: e["code"] for e in body["errors"]}
    assert fields == {"name": "max_length", "age": "min_value"}


@pytest.mark.urls(__name__)
def test_default_permission_is_deny_for_anonymous(client):
    _assert_problem(client.get("/api/v1/_test/protected/"), 403, "not_authenticated")


@pytest.mark.urls(__name__)
def test_unhandled_exception_returns_500_without_internals(client):
    client.raise_request_exception = False
    response = client.get("/api/v1/_test/boom/")
    body = _assert_problem(response, 500, "internal_error")
    assert "hunter2" not in response.content.decode()
    assert "Traceback" not in response.content.decode()
    assert body["detail"] == "An unexpected error occurred."


@pytest.mark.urls(__name__)
def test_malformed_json_is_parse_error(client):
    response = client.post("/api/v1/_test/validate/", "{not json", content_type="application/json")
    _assert_problem(response, 400, "parse_error")


def test_unknown_route_is_problem_details_404(client):
    _assert_problem(client.get("/api/v1/does-not-exist/"), 404, "not_found")


@pytest.mark.parametrize("debug", [True, False])
def test_unknown_api_route_is_problem_details_regardless_of_debug(client, settings, debug):
    settings.DEBUG = debug
    _assert_problem(client.post("/api/v2/anything", {}), 404, "not_found")


def test_unknown_non_api_route_uses_problem_handler(client):
    _assert_problem(client.get("/not-an-api-path"), 404, "not_found")


@pytest.mark.urls(__name__)
def test_method_not_allowed(client):
    _assert_problem(client.delete("/api/v1/_test/validate/"), 405, "method_not_allowed")
