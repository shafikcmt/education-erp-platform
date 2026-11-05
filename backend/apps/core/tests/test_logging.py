import json
import logging.config

import structlog

from apps.core.logging import REDACTED, build_logging_config, redact_sensitive


def test_sensitive_keys_are_redacted_recursively():
    event = {
        "event": "login",
        "password": "hunter2",
        "user": {"email": "a@example.com", "api_key": "k", "nested": [{"session_token": "t"}]},
        "Authorization": "Bearer abc",
    }
    out = redact_sensitive(None, "info", dict(event))
    assert out["password"] == REDACTED
    assert out["Authorization"] == REDACTED
    assert out["user"]["api_key"] == REDACTED
    assert out["user"]["nested"][0]["session_token"] == REDACTED
    assert out["user"]["email"] == "a@example.com"


def test_json_format_emits_one_json_object_with_context(capsys):
    config = build_logging_config(level="INFO", fmt="json")
    logging.config.dictConfig(config)
    structlog.contextvars.bind_contextvars(request_id="req-12345678")
    try:
        structlog.get_logger("erp.test").info("something_happened", secret="s3cr3t", count=3)
    finally:
        structlog.contextvars.clear_contextvars()
        logging.config.dictConfig(build_logging_config(level="WARNING", fmt="console"))
    line = [ln for ln in capsys.readouterr().err.splitlines() if "something_happened" in ln][-1]
    payload = json.loads(line)
    assert payload["event"] == "something_happened"
    assert payload["request_id"] == "req-12345678"
    assert payload["secret"] == REDACTED
    assert payload["count"] == 3
    assert payload["level"] == "info"
