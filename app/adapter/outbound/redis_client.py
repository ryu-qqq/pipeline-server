import hashlib
import json
import os

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_pool: redis.ConnectionPool | None = None

SEARCH_CACHE_TTL = 300  # 5분


def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(REDIS_URL)
    return redis.Redis(connection_pool=_pool)


def get_search_cache(conditions: dict) -> dict | None:
    """검색 조건으로 캐시를 조회한다."""
    r = get_redis()
    key = _build_search_key(conditions)
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    return None


def set_search_cache(conditions: dict, data: dict) -> None:
    """검색 결과를 캐싱한다."""
    r = get_redis()
    key = _build_search_key(conditions)
    r.setex(key, SEARCH_CACHE_TTL, json.dumps(data, default=str))


def invalidate_search_cache() -> None:
    """분석 완료 시 전체 검색 캐시를 무효화한다."""
    r = get_redis()
    keys = r.keys("search:*")
    if keys:
        r.delete(*keys)


def _build_search_key(conditions: dict) -> str:
    """검색 조건을 hash하여 캐시 키를 생성한다."""
    sorted_str = json.dumps(conditions, sort_keys=True, default=str)
    hash_val = hashlib.md5(sorted_str.encode()).hexdigest()
    return f"search:{hash_val}"
