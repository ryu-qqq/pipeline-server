from app.domain.models import SearchCriteria
from app.domain.ports import SearchRepository, SearchResult


class SearchService:
    """학습 데이터 검색 서비스 (Query)"""

    def __init__(self, search_repo: SearchRepository) -> None:
        self._search_repo = search_repo

    def search(self, criteria: SearchCriteria) -> tuple[list[SearchResult], int]:
        return self._search_repo.search(criteria)
