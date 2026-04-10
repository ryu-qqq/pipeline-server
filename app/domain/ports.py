from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator

from app.domain.enums import Stage, TaskStatus
from app.domain.models import (
    AnalyzeTask,
    Label,
    OddTag,
    OutboxCriteria,
    OutboxMessage,
    Rejection,
    RejectionCriteria,
    DataSearchCriteria,
    SearchResult,
    Selection,
)
from app.domain.value_objects import StageProgress

# === MySQL Repository Ports ===


class SelectionRepository(ABC):
    """Selection 저장소 포트 (MySQL)"""

    @abstractmethod
    def save_all(self, selections: list[Selection]) -> int:
        """INSERT IGNORE로 저장하고 실제 적재 건수를 반환한다."""
        ...

    @abstractmethod
    def find_by_id(self, selection_id: int) -> Selection | None: ...

    @abstractmethod
    def find_all_ids_by_task(self, task_id: str) -> set[int]: ...


class OddTagRepository(ABC):
    """ODD 태깅 저장소 포트 (MySQL)"""

    @abstractmethod
    def save_all(self, odd_tags: list[OddTag]) -> int:
        """INSERT IGNORE로 저장하고 실제 적재 건수를 반환한다."""
        ...

    @abstractmethod
    def find_by_video_id(self, video_id: int) -> OddTag | None: ...

    @abstractmethod
    def find_all_video_ids_by_task(self, task_id: str) -> set[int]: ...


class LabelRepository(ABC):
    """자동 라벨링 저장소 포트 (MySQL)"""

    @abstractmethod
    def save_all(self, labels: list[Label]) -> int:
        """INSERT IGNORE로 저장하고 실제 적재 건수를 반환한다."""
        ...

    @abstractmethod
    def find_all_by_video_id(self, video_id: int) -> list[Label]: ...

    @abstractmethod
    def find_all_video_ids_by_task(self, task_id: str) -> set[int]: ...


class RejectionRepository(ABC):
    """거부 레코드 저장소 포트 (MySQL)"""

    @abstractmethod
    def save_all(self, rejections: list[Rejection]) -> None: ...

    @abstractmethod
    def search(self, criteria: RejectionCriteria) -> tuple[list[Rejection], int]: ...


class DataSearchRepository(ABC):
    """학습 데이터 검색 포트 (MySQL)"""

    @abstractmethod
    def search(self, criteria: DataSearchCriteria) -> tuple[list[SearchResult], int]: ...


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
    def find_by_task_and_source(self, task_id: str, source: str) -> Iterator[dict]: ...

    @abstractmethod
    def delete_by_task(self, task_id: str) -> None: ...


class TaskRepository(ABC):
    """분석 작업 상태 저장소 포트 (MongoDB)

    Repository는 저장/조회만 수행한다.
    상태 전이는 도메인 객체(AnalyzeTask)가 담당한다.
    """

    @abstractmethod
    def save(self, task: AnalyzeTask) -> None:
        """도메인 객체를 저장한다. 이미 존재하면 덮어쓴다 (upsert)."""
        ...

    @abstractmethod
    def find_by_id(self, task_id: str) -> AnalyzeTask | None: ...

    @abstractmethod
    def find_by_statuses(self, statuses: list[TaskStatus]) -> AnalyzeTask | None:
        """주어진 상태 중 하나에 해당하는 가장 최근 작업을 반환한다."""
        ...


# === Outbox Port ===


class OutboxRepository(ABC):
    """Outbox 메시지 저장소 포트 (MongoDB)

    Repository는 저장/조회만 수행한다.
    상태 전이는 도메인 객체(OutboxMessage)가 담당한다.
    """

    @abstractmethod
    def save(self, message: OutboxMessage) -> None:
        """도메인 객체를 저장한다. 이미 존재하면 덮어쓴다 (upsert)."""
        ...

    @abstractmethod
    def find_by(self, criteria: "OutboxCriteria") -> list[OutboxMessage]: ...


# === Transaction Port ===


class TransactionManager(ABC):
    """트랜잭션 관리 포트 — 여러 저장소 작업을 원자적으로 실행"""

    @abstractmethod
    def execute(self, fn: "Callable[[], None]") -> None:
        """fn 내부의 모든 저장소 작업을 하나의 트랜잭션으로 묶는다.
        fn이 예외 없이 완료되면 커밋, 예외 시 롤백."""
        ...


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
    def invalidate_all(self) -> None:
        """모든 캐시를 무효화한다."""
        ...
