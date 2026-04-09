import os

import redis as redis_lib

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_pool: redis_lib.ConnectionPool | None = None


def get_redis() -> redis_lib.Redis:
    global _pool
    if _pool is None:
        _pool = redis_lib.ConnectionPool.from_url(REDIS_URL)
    return redis_lib.Redis(connection_pool=_pool)
