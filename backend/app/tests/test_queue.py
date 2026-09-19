from unittest.mock import patch
from redis.exceptions import ConnectionError
from app.queue.redis_queue import sync_task, pop_priority_hint, health


def test_redis_outage_is_a_safe_fallback():
    with patch("app.queue.redis_queue.client", side_effect=ConnectionError("offline")):
        sync_task("task", "org", 50, True)
        assert pop_priority_hint("org") is None
        assert health() == "degraded"


def test_redis_priority_pop_is_atomic():
    with patch("app.queue.redis_queue.client") as client:
        client.return_value.zpopmax.return_value = [("task-1", 95.0)]
        assert pop_priority_hint("org-1") == 95
        client.return_value.zpopmax.assert_called_once_with("argus:queue:org-1")
