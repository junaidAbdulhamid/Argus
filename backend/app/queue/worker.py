"""Separate Redis-woken, database-backed export process."""

import logging
import time
from redis.exceptions import RedisError
from redis import Redis
from app.core.config import settings
from app.services.export_jobs import process_next

logging.basicConfig(level=logging.INFO)


def main():
    while True:
        try:
            if process_next():
                continue
            try:
                Redis.from_url(settings().redis_url, socket_connect_timeout=1, socket_timeout=2).blpop(
                    "argus:exports", timeout=1
                )
            except RedisError:
                time.sleep(1)
        except Exception:
            logging.exception("Worker iteration failed; retrying")
            time.sleep(3)


if __name__ == "__main__":
    main()
