from django.conf import settings

from apps.core.tasks import ping
from config.celery import app


def test_ping_task_runs():
    assert ping.delay().get(timeout=5) == "pong"


def test_celery_uses_json_only_and_safe_defaults():
    conf = app.conf
    assert conf.accept_content == ["json"]
    assert conf.task_serializer == "json"
    assert conf.result_serializer == "json"
    assert conf.task_acks_late is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_default_queue == "default"


def test_beat_schedule_and_queues_declared():
    assert settings.CELERY_BEAT_SCHEDULE["core-heartbeat"]["task"] == "core.ping"
    assert set(settings.CELERY_QUEUES_ALL) == {
        "default",
        "notifications",
        "reports",
        "imports",
        "finance",
        "ai",
    }
