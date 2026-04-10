from app.domain.models import Rejection, RejectionCriteria
from app.domain.ports import RejectionRepository


class RejectionReadService:
    """거부 데이터 조회 서비스 (Query)"""

    def __init__(self, rejection_repo: RejectionRepository) -> None:
        self._rejection_repo = rejection_repo

    def search(self, criteria: RejectionCriteria) -> tuple[list[Rejection], int]:
        return self._rejection_repo.search(criteria)
