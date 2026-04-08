from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.models import Label, OddTag, Rejection, RejectionCriteria, SearchCriteria, Selection


class SelectionRepository(ABC):
    """Selection 저장소 포트"""

    @abstractmethod
    def save_all(self, selections: list[Selection]) -> None: ...

    @abstractmethod
    def find_by_id(self, selection_id: int) -> Selection | None: ...

    @abstractmethod
    def find_all_ids(self) -> set[int]: ...

    @abstractmethod
    def delete_all(self) -> None: ...


class OddTagRepository(ABC):
    """ODD 태깅 저장소 포트"""

    @abstractmethod
    def save_all(self, odd_tags: list[OddTag]) -> None: ...

    @abstractmethod
    def find_by_video_id(self, video_id: int) -> OddTag | None: ...

    @abstractmethod
    def find_all_video_ids(self) -> set[int]: ...

    @abstractmethod
    def delete_all(self) -> None: ...


class LabelRepository(ABC):
    """자동 라벨링 저장소 포트"""

    @abstractmethod
    def save_all(self, labels: list[Label]) -> None: ...

    @abstractmethod
    def find_all_by_video_id(self, video_id: int) -> list[Label]: ...

    @abstractmethod
    def find_all_video_ids(self) -> set[int]: ...

    @abstractmethod
    def delete_all(self) -> None: ...


class RejectionRepository(ABC):
    """거부 레코드 저장소 포트"""

    @abstractmethod
    def save_all(self, rejections: list[Rejection]) -> None: ...

    @abstractmethod
    def search(self, criteria: RejectionCriteria) -> tuple[list[Rejection], int]: ...

    @abstractmethod
    def delete_all(self) -> None: ...


@dataclass(frozen=True)
class SearchResult:
    """검색 결과 한 건 (Selection + OddTag + Labels 통합)"""

    selection: Selection
    odd_tag: OddTag | None
    labels: list[Label]


class SearchRepository(ABC):
    """학습 데이터 검색 포트"""

    @abstractmethod
    def search(self, criteria: SearchCriteria) -> tuple[list[SearchResult], int]: ...
