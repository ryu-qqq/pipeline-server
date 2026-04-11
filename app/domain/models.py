import dataclasses
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from app.domain.enums import (
    ObjectClass,
    OutboxStatus,
    RejectionReason,
    RoadSurface,
    Stage,
    TaskStatus,
    TimeOfDay,
    Weather,
)
from app.domain.exceptions import InvalidFormatError, InvalidOddTagError
from app.domain.value_objects import (
    Confidence,
    ObjectCount,
    SourcePath,
    StageProgress,
    StageResult,
    Temperature,
    VideoId,
    WiperState,
)


@dataclass(frozen=True)
class Selection:
    """선별된 영상 메타데이터 (v1/v2 통합 모델)"""

    id: VideoId
    task_id: str
    recorded_at: datetime
    temperature: Temperature
    wiper: WiperState
    headlights_on: bool
    source_path: SourcePath

    def is_night_driving(self) -> bool:
        """야간 주행 여부를 센서 데이터로 판단한다."""
        return self.headlights_on

    def is_adverse_weather_likely(self) -> bool:
        """악천후 가능성을 센서 데이터로 판단한다."""
        return self.wiper.is_raining_likely() or self.temperature.celsius < 0


@dataclass(frozen=True)
class OddTag:
    """ODD 태깅 결과 (사람이 직접 태깅)"""

    id: int
    task_id: str
    video_id: VideoId
    weather: Weather
    time_of_day: TimeOfDay
    road_surface: RoadSurface

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise InvalidOddTagError(f"id는 양수여야 합니다: {self.id}")

    def is_hazardous(self) -> bool:
        """위험 주행 환경인지 판단한다."""
        return self.road_surface in (RoadSurface.ICY, RoadSurface.SNOWY) or self.weather == Weather.SNOWY

    def is_low_visibility(self) -> bool:
        """저시정 환경인지 판단한다."""
        return self.time_of_day == TimeOfDay.NIGHT or self.weather in (Weather.RAINY, Weather.SNOWY)


@dataclass(frozen=True)
class Label:
    """자동 라벨링 결과 (딥러닝 모델 추론)"""

    task_id: str
    video_id: VideoId
    object_class: ObjectClass
    obj_count: ObjectCount
    confidence: Confidence
    labeled_at: datetime

    def is_reliable(self, threshold: float = 0.8) -> bool:
        """신뢰할 수 있는 라벨인지 판단한다."""
        return self.confidence.is_high(threshold)

    def has_objects(self) -> bool:
        """객체가 탐지되었는지 판단한다."""
        return not self.obj_count.is_empty()


@dataclass(frozen=True)
class Rejection:
    """정제 과정에서 거부된 레코드

    원본 데이터는 MongoDB raw_data 컬렉션에 task_id + source로 보관되어 있다.
    source_id를 통해 원본 row를 특정할 수 있다.
    """

    task_id: str
    stage: Stage
    reason: RejectionReason
    source_id: str
    field: str
    detail: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.source_id:
            raise InvalidFormatError("source_id는 비어있을 수 없습니다")
        if not self.detail:
            raise InvalidFormatError("detail은 비어있을 수 없습니다")


@dataclass(frozen=True)
class RejectionCriteria:
    """거부 데이터 조회 조건"""

    task_id: str | None = None
    stage: Stage | None = None
    reason: RejectionReason | None = None
    source_id: str | None = None
    field: str | None = None
    page: int | None = 1
    size: int = 20
    after: int | None = None


@dataclass(frozen=True)
class DataSearchCriteria:
    """학습 데이터 검색 조건"""

    task_id: str | None = None

    # Selection 조건
    recorded_at_from: datetime | None = None
    recorded_at_to: datetime | None = None
    min_temperature: float | None = None
    max_temperature: float | None = None
    headlights_on: bool | None = None

    # ODD 조건
    weather: Weather | None = None
    time_of_day: TimeOfDay | None = None
    road_surface: RoadSurface | None = None

    # Label 조건
    object_class: ObjectClass | None = None
    min_obj_count: int | None = None
    min_confidence: float | None = None

    page: int | None = 1
    size: int = 20
    after: int | None = None


@dataclass(frozen=True)
class AnalysisResult:
    """POST /analyze 응답용 분석 결과"""

    selection: StageResult
    odd_tagging: StageResult
    auto_labeling: StageResult
    fully_linked: int
    partial: int


# === 검색 결과 모델 ===


@dataclass(frozen=True)
class SearchResult:
    """검색 결과 한 건 (Selection + OddTag + Labels 통합)"""

    selection: Selection
    odd_tag: OddTag | None
    labels: list[Label]


# === 분석 작업 모델 ===


@dataclass(frozen=True)
class AnalyzeTask:
    """분석 작업 상태"""

    task_id: str
    status: TaskStatus
    selection_progress: StageProgress
    odd_tagging_progress: StageProgress
    auto_labeling_progress: StageProgress
    last_completed_phase: Stage | None = None
    result: "AnalysisResult | None" = None
    error: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def create_new(
        cls,
        task_id: str,
        selection_count: int,
        odd_count: int,
        label_count: int,
    ) -> "AnalyzeTask":
        """신규 분석 작업을 생성한다."""
        return cls(
            task_id=task_id,
            status=TaskStatus.PENDING,
            selection_progress=StageProgress(total=selection_count),
            odd_tagging_progress=StageProgress(total=odd_count),
            auto_labeling_progress=StageProgress(total=label_count),
            created_at=datetime.now(),
        )

    # Phase 실행 순서 (ClassVar — dataclass 필드가 아닌 클래스 상수)
    _STAGE_ORDER: ClassVar[list[Stage]] = [Stage.SELECTION, Stage.ODD_TAGGING, Stage.AUTO_LABELING]

    def is_active(self) -> bool:
        """진행 중인 작업인지 판단한다."""
        return self.status in (TaskStatus.PENDING, TaskStatus.PROCESSING)

    def should_run_phase(self, phase: Stage) -> bool:
        """해당 Phase를 실행해야 하는지 판단한다.

        last_completed_phase가 None이면 모든 Phase 실행.
        설정되어 있으면 해당 Phase 이후의 Phase만 실행.
        """
        if self.last_completed_phase is None:
            return True
        return self._STAGE_ORDER.index(phase) > self._STAGE_ORDER.index(self.last_completed_phase)

    def get_progress_for(self, stage: Stage) -> StageProgress:
        """특정 단계의 진행률을 반환한다."""
        progress_map = {
            Stage.SELECTION: self.selection_progress,
            Stage.ODD_TAGGING: self.odd_tagging_progress,
            Stage.AUTO_LABELING: self.auto_labeling_progress,
        }
        return progress_map.get(stage, StageProgress())

    # === 상태 전이 메서드 ===

    def start_processing(self) -> "AnalyzeTask":
        """정제 파이프라인 시작 시 PROCESSING으로 전환한다."""
        return dataclasses.replace(self, status=TaskStatus.PROCESSING)

    def complete_with(self, result: "AnalysisResult") -> "AnalyzeTask":
        """정제 완료 시 결과를 포함하여 COMPLETED로 전환한다."""
        return dataclasses.replace(
            self, status=TaskStatus.COMPLETED, result=result, completed_at=datetime.now(),
        )

    def fail_with(self, error: str) -> "AnalyzeTask":
        """실패 시 에러 메시지를 포함하여 FAILED로 전환한다."""
        return dataclasses.replace(
            self, status=TaskStatus.FAILED, error=error, completed_at=datetime.now(),
        )

    def with_progress(self, stage: Stage, progress: StageProgress) -> "AnalyzeTask":
        """특정 단계의 진행률을 갱신한다."""
        field_map = {
            Stage.SELECTION: "selection_progress",
            Stage.ODD_TAGGING: "odd_tagging_progress",
            Stage.AUTO_LABELING: "auto_labeling_progress",
        }
        field_name = field_map[stage]
        return dataclasses.replace(self, **{field_name: progress})

    def with_completed_phase(self, phase: Stage) -> "AnalyzeTask":
        """완료된 Phase를 기록한다 (resume 포인트)."""
        return dataclasses.replace(self, last_completed_phase=phase)


# === Outbox 모델 ===


@dataclass(frozen=True)
class OutboxCriteria:
    """Outbox 메시지 조회 조건"""

    status: OutboxStatus
    before: datetime | None = None
    limit: int = 10


@dataclass(frozen=True)
class OutboxMessage:
    """Outbox 메시지 — MongoDB 트랜잭션으로 도메인 이벤트 발행을 보장"""

    message_id: str
    message_type: str
    payload: dict
    status: OutboxStatus = OutboxStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def create_analyze_event(cls, message_id: str, task_id: str) -> "OutboxMessage":
        """분석 작업 발행 이벤트를 생성한다."""
        now = datetime.now()
        return cls(
            message_id=message_id,
            message_type="ANALYZE",
            payload={"task_id": task_id},
            created_at=now,
            updated_at=now,
        )

    def is_retriable(self) -> bool:
        """재시도 가능한지 판단한다."""
        return self.retry_count < self.max_retries

    # === 상태 전이 메서드 (frozen이므로 새 인스턴스 반환) ===

    def mark_processing(self) -> "OutboxMessage":
        """발행 시도 전 PROCESSING으로 전환한다."""
        return dataclasses.replace(self, status=OutboxStatus.PROCESSING, updated_at=datetime.now())

    def mark_published(self) -> "OutboxMessage":
        """발행 성공 시 PUBLISHED로 전환한다."""
        return dataclasses.replace(self, status=OutboxStatus.PUBLISHED, updated_at=datetime.now())

    def mark_failed(self) -> "OutboxMessage":
        """최종 실패 처리한다."""
        return dataclasses.replace(self, status=OutboxStatus.FAILED, updated_at=datetime.now())

    def back_to_pending(self) -> "OutboxMessage":
        """좀비 복구 — 재시도를 위해 PENDING으로 되돌린다."""
        return dataclasses.replace(self, status=OutboxStatus.PENDING, updated_at=datetime.now())

    def with_retry_incremented(self) -> "OutboxMessage":
        """재시도 횟수를 1 증가시킨다."""
        return dataclasses.replace(self, retry_count=self.retry_count + 1, updated_at=datetime.now())


