from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import (
    ObjectClass,
    RejectionReason,
    RoadSurface,
    Stage,
    TaskStatus,
    TimeOfDay,
    Weather,
)
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
    video_id: VideoId
    weather: Weather
    time_of_day: TimeOfDay
    road_surface: RoadSurface

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError(f"id는 양수여야 합니다: {self.id}")

    def is_hazardous(self) -> bool:
        """위험 주행 환경인지 판단한다."""
        return self.road_surface in (RoadSurface.ICY, RoadSurface.SNOWY) or self.weather == Weather.SNOWY

    def is_low_visibility(self) -> bool:
        """저시정 환경인지 판단한다."""
        return self.time_of_day == TimeOfDay.NIGHT or self.weather in (Weather.RAINY, Weather.SNOWY)


@dataclass(frozen=True)
class Label:
    """자동 라벨링 결과 (딥러닝 모델 추론)"""

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
    """정제 과정에서 거부된 레코드"""

    record_identifier: str
    stage: Stage
    reason: RejectionReason
    detail: str
    raw_data: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.record_identifier:
            raise ValueError("record_identifier는 비어있을 수 없습니다")
        if not self.detail:
            raise ValueError("detail은 비어있을 수 없습니다")


@dataclass(frozen=True)
class RejectionCriteria:
    """거부 데이터 조회 조건"""

    stage: Stage | None = None
    reason: RejectionReason | None = None
    page: int = 1
    size: int = 20


@dataclass(frozen=True)
class SearchCriteria:
    """학습 데이터 검색 조건"""

    weather: Weather | None = None
    time_of_day: TimeOfDay | None = None
    road_surface: RoadSurface | None = None
    object_class: ObjectClass | None = None
    min_obj_count: int | None = None
    min_confidence: float | None = None
    page: int = 1
    size: int = 20


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
    result: dict | None = None
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
