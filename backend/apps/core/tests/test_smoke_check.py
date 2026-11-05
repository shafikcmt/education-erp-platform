import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.management.commands import smoke_check

pytestmark = pytest.mark.django_db


def test_smoke_check_passes_in_test_environment():
    out = StringIO()
    call_command("smoke_check", stdout=out)
    report = json.loads(out.getvalue())
    assert report["database"]["ok"] and report["database"]["user"] == "erp_app"
    assert report["cache"]["ok"]
    assert report["storage"] == {"ok": True, "roundtrip": True, "exists_after_delete": False}
    assert report["celery"] == {"ok": True, "result": "pong"}


def test_smoke_check_reports_all_failures_and_exits_nonzero(monkeypatch):
    def broken():
        raise RuntimeError("broker down")

    monkeypatch.setitem(smoke_check.CHECKS, "celery", broken)
    out = StringIO()
    with pytest.raises(CommandError, match="smoke check failed"):
        call_command("smoke_check", stdout=out)
    report = json.loads(out.getvalue())
    assert report["celery"] == {"ok": False, "error": "broker down"}
    assert report["database"]["ok"] is True


def test_smoke_check_skip(monkeypatch):
    out = StringIO()
    call_command("smoke_check", "--skip", "celery", "--skip", "storage", stdout=out)
    report = json.loads(out.getvalue())
    assert report["celery"] == {"skipped": True}
