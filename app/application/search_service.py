import dataclasses
import hashlib
import json
import logging
from datetime import datetime

from app.domain.enums import ObjectClass, RoadSurface, TimeOfDay, Weather
from app.domain.models import Label, OddTag, SearchCriteria, Selection
from app.domain.ports import CacheRepository, SearchRepository, SearchResult
from app.domain.value_objects import Confidence, ObjectCount, SourcePath, Temperature, VideoId, WiperState

logger = logging.getLogger(__name__)

SEARCH_CACHE_TTL = 300  # 5분


class SearchService:
    """학습 데이터 검색 서비스 (Query)"""

    def __init__(self, search_repo: SearchRepository, cache_repo: CacheRepository) -> None:
        self._search_repo = search_repo
        self._cache_repo = cache_repo

    def search(self, criteria: SearchCriteria) -> tuple[list[SearchResult], int]:
        cache_key = self._build_cache_key(criteria)

        cached = self._cache_repo.get(cache_key)
        if cached is not None:
            logger.debug("캐시 hit: key=%s", cache_key)
            return self._deserialize(cached)

        results, total = self._search_repo.search(criteria)

        self._cache_repo.set(cache_key, self._serialize(results, total), SEARCH_CACHE_TTL)
        logger.debug("캐시 miss → 저장: key=%s, total=%d", cache_key, total)
        return results, total

    @staticmethod
    def _build_cache_key(criteria: SearchCriteria) -> str:
        key_data = dataclasses.asdict(criteria)
        sorted_str = json.dumps(key_data, sort_keys=True, default=str)
        hash_val = hashlib.md5(sorted_str.encode()).hexdigest()
        return f"search:{hash_val}"

    @staticmethod
    def _serialize(results: list[SearchResult], total: int) -> dict:
        return {
            "results": [dataclasses.asdict(r) for r in results],
            "total": total,
        }

    @staticmethod
    def _deserialize(cached: dict) -> tuple[list[SearchResult], int]:
        total = cached["total"]
        results = [SearchService._to_search_result(r) for r in cached["results"]]
        return results, total

    @staticmethod
    def _to_search_result(data: dict) -> SearchResult:
        sel = data["selection"]
        selection = Selection(
            id=VideoId(sel["id"]["value"]),
            recorded_at=datetime.fromisoformat(sel["recorded_at"]),
            temperature=Temperature(celsius=sel["temperature"]["celsius"]),
            wiper=WiperState(active=sel["wiper"]["active"], level=sel["wiper"]["level"]),
            headlights_on=sel["headlights_on"],
            source_path=SourcePath(sel["source_path"]["value"]),
        )

        odd_tag = None
        if data["odd_tag"] is not None:
            ot = data["odd_tag"]
            odd_tag = OddTag(
                id=ot["id"],
                video_id=VideoId(ot["video_id"]["value"]),
                weather=Weather(ot["weather"]),
                time_of_day=TimeOfDay(ot["time_of_day"]),
                road_surface=RoadSurface(ot["road_surface"]),
            )

        labels = [
            Label(
                video_id=VideoId(lb["video_id"]["value"]),
                object_class=ObjectClass(lb["object_class"]),
                obj_count=ObjectCount(lb["obj_count"]["value"]),
                confidence=Confidence(lb["confidence"]["value"]),
                labeled_at=datetime.fromisoformat(lb["labeled_at"]),
            )
            for lb in data["labels"]
        ]

        return SearchResult(selection=selection, odd_tag=odd_tag, labels=labels)
