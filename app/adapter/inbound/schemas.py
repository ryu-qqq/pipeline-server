import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

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
    """페이지네이션 응답"""

    content: list[T]
    page: int
    size: int
    total_elements: int
    total_pages: int
    first: bool
    last: bool
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


# === Request DTO (= Spring @ModelAttribute) ===


class RejectionSearchRequest(BaseModel):
    """GET /rejections 조회 요청"""

    stage: Stage | None = None
    reason: RejectionReason | None = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class DataSearchRequest(BaseModel):
    """GET /search 검색 요청"""

    weather: Weather | None = None
    time_of_day: TimeOfDay | None = None
    road_surface: RoadSurface | None = None
    object_class: ObjectClass | None = None
    min_obj_count: int | None = Field(None, ge=0)
    min_confidence: float | None = Field(None, ge=0.0, le=1.0)
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


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
    record_identifier: str
    stage: str
    reason: str
    detail: str
    raw_data: str | None = None
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
