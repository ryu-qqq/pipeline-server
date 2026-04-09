import json
from datetime import datetime


class RedisSerializer:
    """Redis 값 직렬화/역직렬화"""

    @staticmethod
    def serialize(data: dict | list) -> str:
        return json.dumps(data, ensure_ascii=False, default=_json_default)

    @staticmethod
    def deserialize(raw: str | bytes) -> dict | list:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"직렬화 불가: {type(obj)}")
