"""Redis-backed single-flight lock for Celery beat tasks.

If a task is already running and the beat fires again, the new invocation
exits immediately instead of starting a concurrent run that would race on
the DB. The lock auto-expires so a crashed worker cannot wedge the schedule.
"""

import logging
from functools import wraps

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_client = redis.Redis.from_url(settings.redis_url)


def single_flight(name: str, timeout: int):
    """Decorator: only one concurrent run of this task across workers.

    `timeout` must exceed the task's time_limit so a killed task's lock
    still expires on its own.
    """

    def outer(fn):
        @wraps(fn)
        def inner(self, *args, **kwargs):
            key = f"doornegar:lock:{name}"
            acquired = _client.set(key, "1", nx=True, ex=timeout)
            if not acquired:
                logger.info("Skip %s: another run holds the lock", name)
                return {"skipped": "another_run_in_progress"}
            try:
                return fn(self, *args, **kwargs)
            finally:
                _client.delete(key)

        return inner

    return outer
