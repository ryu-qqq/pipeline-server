from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import Stage, TaskStatus
from app.domain.models import Label, OddTag, Rejection, RejectionCriteria, SearchCriteria, Selection

# === MySQL Repository Ports ===


class SelectionRepository(ABC):
    """Selection 저장소 포트 (MySQL)"""

    @abstractmethod
    def save_all(self, selections: list[Selection]) -> None: ...

    @abstractmethod
    def find_by_id(self, selection_id: int) -> Selection | None: ...

    @abstractmethod
    def find_all_ids(self) -> set[int]: ...

    @abstractmethod
    def delete_all(self) -> None: ...


class OddTagRepository(ABC):
    """ODD 태깅 저장소 포트 (MySQL)"""

    @abstractmethod
    def save_all(self, odd_tags: list[OddTag]) -> None: ...

    @abstractmethod
    def find_by_video_id(self, video_id: int) -> OddTag | None: ...

    @abstractmethod
    def find_all_video_ids(self) -> set[int]: ...

    @abstractmethod
    def delete_all(self) -> None: ...


class LabelRepository(ABC):
    """자동 라벨링 저장소 포트 (MySQL)"""

    @abstractmethod
    def save_all(self, labels: list[Label]) -> None: ...

    @abstractmethod
    def find_all_by_video_id(self, video_id: int) -> list[Label]: ...

    @abstractmethod
    def find_all_video_ids(self) -> set[int]: ...

    @abstractmethod
    def delete_all(self) -> None: ...


class RejectionRepository(ABC):
    """거부 레코드 저장소 포트 (MySQL)"""

    @abstractmethod
    def save_all(self, rejections: list[Rejection]) -> None: ...

    @abstractmethod
    def search(self, criteria: RejectionCriteria) -> tuple[list[Rejection], int]: ...

    @abstractmethod
    def delete_all(self) -> None: ...


# === 검색 결과 모델 ===


@dataclass(frozen=True)
class SearchResult:
    """검색 결과 한 건 (Selection + OddTag + Labels 통합)"""

    selection: Selection
    odd_tag: OddTag | None
    labels: list[Label]


class SearchRepository(ABC):
    """학습 데이터 검색 포트 (MySQL)"""

    @abstractmethod
    def search(self, criteria: SearchCriteria) -> tuple[list[SearchResult], int]: ...


# === MongoDB Repository Ports ===


@dataclass(frozen=True)
class StageProgress:
    """단계별 진행률"""

    total: int = 0
    processed: int = 0
    rejected: int = 0

    @property
    def percent(self) -> float:
        return round((self.processed + self.rejected) / self.total * 100, 1) if self.total > 0 else 0.0


@dataclass(frozen=True)
class AnalyzeTask:
    """분석 작업 상태"""

    task_id: str
    status: TaskStatus
    selection_progress: StageProgress
    odd_tagging_progress: StageProgress
    auto_labeling_progress: StageProgress
    result: dict | None = None
    error: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class RawDataRepository(ABC):
    """원본 데이터 저장소 포트 (MongoDB)"""

    @abstractmethod
    def save_raw_selections(self, task_id: str, raw_list: list[dict]) -> int: ...

    @abstractmethod
    def save_raw_odds(self, task_id: str, rows: list[dict]) -> int: ...

    @abstractmethod
    def save_raw_labels(self, task_id: str, rows: list[dict]) -> int: ...

    @abstractmethod
    def find_by_task_and_source(self, task_id: str, source: str) -> list[dict]: ...

    @abstractmethod
    def delete_by_task(self, task_id: str) -> None: ...


class TaskRepository(ABC):
    """분석 작업 상태 저장소 포트 (MongoDB)"""

    @abstractmethod
    def create(self, task: AnalyzeTask) -> None: ...

    @abstractmethod
    def find_by_id(self, task_id: str) -> AnalyzeTask | None: ...

    @abstractmethod
    def update_status(self, task_id: str, status: TaskStatus) -> None: ...

    @abstractmethod
    def update_progress(self, task_id: str, stage: Stage, progress: StageProgress) -> None: ...

    @abstractmethod
    def complete(self, task_id: str, result: dict) -> None: ...

    @abstractmethod
    def fail(self, task_id: str, error: str) -> None: ...


# === Task Dispatch Port ===


class TaskDispatcher(ABC):
    """비동기 작업 발행 포트"""

    @abstractmethod
    def dispatch(self, task_id: str) -> None: ...


# === Redis Cache Ports ===


class CacheRepository(ABC):
    """캐시 저장소 포트 (Redis)"""

    @abstractmethod
    def get(self, key: str) -> dict | None: ...

    @abstractmethod
    def set(self, key: str, data: dict, ttl: int) -> None: ...

    @abstractmethod
    def invalidate_pattern(self, pattern: str) -> None: ...
