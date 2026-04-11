import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import (
    ObjectClass,
    RejectionReason,
    RoadSurface,
    Stage,
    TimeOfDay,
    Weather,
)

T = TypeVar("T")


# === 성공 응답 ===


class ApiResponse(BaseModel, Generic[T]):
    """공통 성공 응답"""

    data: T | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class PageApiResponse(BaseModel, Generic[T]):
    """페이지네이션 응답 — offset(page) 또는 cursor(after) 방식 지원"""

    content: list[T]
    page: int | None = None
    size: int = 20
    total_elements: int = 0
    total_pages: int | None = None
    first: bool | None = None
    last: bool | None = None
    next_after: int | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def of(cls, items: list[T], total: int, page: int, size: int) -> "PageApiResponse[T]":
        total_pages = (total + size - 1) // size if size > 0 else 0
        return cls(
            content=items,
            page=page,
            size=size,
            total_elements=total,
            total_pages=total_pages,
            first=page <= 1,
            last=page >= total_pages,
        )

    @classmethod
    def of_cursor(cls, items: list[T], size: int, last_id: int | None) -> "PageApiResponse[T]":
        return cls(
            content=items,
            size=size,
            next_after=last_id,
        )


# === 에러 응답 (RFC 7807) ===


class ProblemDetail(BaseModel):
    """RFC 7807 에러 응답"""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str | None = None
    instance: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
    errors: dict[str, str] | None = None


# === Task 응답 ===


class StageProgressResponse(BaseModel):
    total: int
    processed: int
    rejected: int
    percent: float


class TaskProgressResponse(BaseModel):
    selection: StageProgressResponse
    odd_tagging: StageProgressResponse
    auto_labeling: StageProgressResponse


class TaskResponse(BaseModel):
    task_id: str
    status: str
    progress: TaskProgressResponse
    result: "AnalysisResponse | None" = None
    error: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class TaskSubmitResponse(BaseModel):
    task_id: str
    status: str


# === Request DTO (= Spring @ModelAttribute) ===


class RejectionSearchRequest(BaseModel):
    """GET /rejections 조회 요청 — page(offset) 또는 after(cursor) 중 하나만 사용"""

    task_id: str | None = None
    stage: Stage | None = None
    reason: RejectionReason | None = None
    source_id: str | None = None
    field: str | None = None
    page: int | None = Field(None, ge=1)
    size: int = Field(20, ge=1, le=100)
    after: int | None = None

    @model_validator(mode="after")
    def _validate_pagination(self) -> "RejectionSearchRequest":
        if self.page is not None and self.after is not None:
            raise ValueError("page와 after는 동시에 사용할 수 없습니다")
        if self.page is None and self.after is None:
            object.__setattr__(self, "page", 1)
        return self


class DataSearchRequest(BaseModel):
    """GET /data 검색 요청 — page(offset) 또는 after(cursor) 중 하나만 사용"""

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
    min_obj_count: int | None = Field(None, ge=0)
    min_confidence: float | None = Field(None, ge=0.0, le=1.0)

    page: int | None = Field(None, ge=1)
    size: int = Field(20, ge=1, le=100)
    after: int | None = None

    @model_validator(mode="after")
    def _validate_pagination(self) -> "DataSearchRequest":
        if self.page is not None and self.after is not None:
            raise ValueError("page와 after는 동시에 사용할 수 없습니다")
        if self.page is None and self.after is None:
            object.__setattr__(self, "page", 1)
        return self


# === Response DTO ===


class StageResultResponse(BaseModel):
    total: int
    loaded: int
    rejected: int


class AnalysisResponse(BaseModel):
    selection: StageResultResponse
    odd_tagging: StageResultResponse
    auto_labeling: StageResultResponse
    fully_linked: int
    partial: int


class RejectionResponse(BaseModel):
    stage: str
    reason: str
    source_id: str
    field: str
    detail: str
    created_at: datetime | None = None


class LabelResponse(BaseModel):
    object_class: str
    obj_count: int
    avg_confidence: float


class SearchResultResponse(BaseModel):
    video_id: int
    recorded_at: datetime
    temperature_celsius: float
    wiper_active: bool
    wiper_level: int | None = None
    headlights_on: bool
    source_path: str
    weather: str | None = None
    time_of_day: str | None = None
    road_surface: str | None = None
    labels: list[LabelResponse] = Field(default_factory=list)


# Forward reference 해결 (TaskResponse가 AnalysisResponse보다 먼저 정의됨)
TaskResponse.model_rebuild()
