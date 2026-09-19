import logging
from redis import Redis, RedisError
from app.core.config import settings

logger = logging.getLogger(__name__)


def client():
    return Redis.from_url(settings().redis_url, socket_connect_timeout=0.3, socket_timeout=0.3, decode_responses=True)


def sync_task(task_id, organization_id, priority, queued):
    try:
        redis = client()
        key = f"argus:queue:{organization_id}"
        if queued:
            redis.zadd(key, {task_id: priority})
        else:
            redis.zrem(key, task_id)
    except RedisError:
        logger.warning("Redis unavailable; PostgreSQL queue remains authoritative")


def health():
    try:
        return "healthy" if client().ping() else "degraded"
    except RedisError:
        return "degraded"


def pop_priority_hint(organization_id):
    """Atomic queue coordination; stale hints are validated against PostgreSQL."""
    try:
        entries = client().zpopmax(f"argus:queue:{organization_id}")
        return int(entries[0][1]) if entries else None
    except RedisError:
        logger.warning("Redis claim hint unavailable; using the database queue")
        return None
