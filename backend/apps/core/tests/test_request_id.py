import uuid
from typing import Any

import pytest
import structlog
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import RequestIDMiddleware, get_request_id

pytestmark = pytest.mark.django_db


def test_request_id_generated_when_absent(client):
    response = client.get("/healthz")
    request_id = response["X-Request-ID"]
    assert uuid.UUID(request_id).version == 7


def test_valid_incoming_request_id_is_propagated(client):
    response = client.get("/healthz", headers={"X-Request-ID": "nginx-0123456789abcdef"})
    assert response["X-Request-ID"] == "nginx-0123456789abcdef"


@pytest.mark.parametrize(
    "bad", ["short", "has spaces in it!!", "x" * 200, "<script>alert(1)</script>"]
)
def test_unsafe_incoming_request_id_is_replaced(client, bad):
    response = client.get("/healthz", headers={"X-Request-ID": bad})
    assert response["X-Request-ID"] != bad
    assert uuid.UUID(response["X-Request-ID"]).version == 7


def test_request_id_is_bound_to_log_context_during_request():
    seen: dict[str, Any] = {}

    def view(request):
        seen["ctx"] = structlog.contextvars.get_contextvars()
        seen["rid"] = get_request_id(request)
        return HttpResponse("ok")

    middleware = RequestIDMiddleware(view)
    response = middleware(RequestFactory().get("/x", headers={"X-Request-ID": "req-abcdefgh"}))
    assert seen["ctx"]["request_id"] == "req-abcdefgh"
    assert seen["rid"] == "req-abcdefgh"
    assert response["X-Request-ID"] == "req-abcdefgh"
    assert "request_id" not in structlog.contextvars.get_contextvars()
