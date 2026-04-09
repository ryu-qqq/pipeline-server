import hashlib
import json

import redis as redis_lib

from app.adapter.outbound.redis.serializer import RedisSerializer
from app.domain.ports import CacheRepository

SEARCH_CACHE_TTL = 300  # 5분


class RedisCacheRepository(CacheRepository):
    """Redis 캐시 저장소 구현체"""

    def __init__(self, client: redis_lib.Redis) -> None:
        self._client = client
        self._serializer = RedisSerializer()

    def get(self, key: str) -> dict | None:
        cached = self._client.get(key)
        if cached is None:
            return None
        return self._serializer.deserialize(cached)

    def set(self, key: str, data: dict, ttl: int = SEARCH_CACHE_TTL) -> None:
        serialized = self._serializer.serialize(data)
        self._client.setex(key, ttl, serialized)

    def invalidate_pattern(self, pattern: str) -> None:
        keys = self._client.keys(pattern)
        if keys:
            self._client.delete(*keys)

    @staticmethod
    def build_search_key(conditions: dict) -> str:
        """검색 조건을 hash하여 캐시 키를 생성한다."""
        sorted_str = json.dumps(conditions, sort_keys=True, default=str)
        hash_val = hashlib.md5(sorted_str.encode()).hexdigest()
        return f"search:{hash_val}"
