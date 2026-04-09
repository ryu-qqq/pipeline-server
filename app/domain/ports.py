from abc import ABC, abstractmethod

from app.domain.enums import Stage, TaskStatus
from app.domain.models import (
    AnalyzeTask,
    Label,
    OddTag,
    OutboxMessage,
    Rejection,
    RejectionCriteria,
    SearchCriteria,
    SearchResult,
    Selection,
)
from app.domain.value_objects import StageProgress

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


class SearchRepository(ABC):
    """학습 데이터 검색 포트 (MySQL)"""

    @abstractmethod
    def search(self, criteria: SearchCriteria) -> tuple[list[SearchResult], int]: ...


# === MongoDB Repository Ports ===


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

    @abstractmethod
    def update_last_completed_phase(self, task_id: str, phase: Stage) -> None: ...


# === Outbox Port ===


class OutboxRepository(ABC):
    """Outbox 메시지 저장소 포트 (MongoDB)"""

    @abstractmethod
    def save(self, message: OutboxMessage) -> None: ...

    @abstractmethod
    def find_pending(self, limit: int = 10) -> list[OutboxMessage]: ...

    @abstractmethod
    def mark_published(self, message_id: str) -> None: ...

    @abstractmethod
    def mark_failed(self, message_id: str) -> None: ...

    @abstractmethod
    def increment_retry(self, message_id: str) -> None: ...


# === Task Dispatch Port ===


class TaskDispatcher(ABC):
    """비동기 작업 발행 포트"""

    @abstractmethod
    def dispatch(self, task_id: str) -> None: ...


# === ID 생성 Port ===


class IdGenerator(ABC):
    """고유 식별자 생성 포트"""

    @abstractmethod
    def generate(self) -> str: ...


# === Redis Cache Ports ===


class CacheRepository(ABC):
    """캐시 저장소 포트 (Redis)"""

    @abstractmethod
    def get(self, key: str) -> dict | None: ...

    @abstractmethod
    def set(self, key: str, data: dict, ttl: int) -> None: ...

    @abstractmethod
    def invalidate_pattern(self, pattern: str) -> None: ...
