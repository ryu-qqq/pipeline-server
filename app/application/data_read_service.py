import logging

from app.domain.models import DataSearchCriteria, SearchResult
from app.domain.ports import DataSearchRepository

logger = logging.getLogger(__name__)


class DataReadService:
    """학습 데이터 검색 서비스 (Query)"""

    def __init__(self, search_repo: DataSearchRepository) -> None:
        self._search_repo = search_repo

    def search(self, criteria: DataSearchCriteria) -> tuple[list[SearchResult], int]:
        return self._search_repo.search(criteria)
