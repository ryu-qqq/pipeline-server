"""adapter 레이어 테스트 공통 fixture"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.adapter.outbound.mysql.database import Base
from app.dependencies import (
    get_analysis_service,
    get_data_read_service,
    get_rejection_read_service,
    get_task_read_service,
)
from app.domain.enums import (
    ObjectClass,
    RejectionReason,
    RoadSurface,
    Stage,
    TimeOfDay,
    Weather,
)
from app.domain.models import Label, OddTag, Rejection, Selection
from app.domain.value_objects import (
    Confidence,
    ObjectCount,
    SourcePath,
    Temperature,
    VideoId,
    WiperState,
)
from app.main import app


# === SQLite in-memory DB ===


@pytest.fixture()
def db_engine():
    """SQLite in-memory 엔진을 생성한다."""
    engine = create_engine("sqlite:///:memory:")

    # SQLite에서 외래 키 활성화
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """테스트 단위 DB 세션을 제공한다."""
    _SessionLocal = sessionmaker(bind=db_engine)
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# === FastAPI TestClient ===


@pytest.fixture()
def mock_analysis_service():
    return MagicMock()


@pytest.fixture()
def mock_task_read_service():
    return MagicMock()


@pytest.fixture()
def mock_rejection_read_service():
    return MagicMock()


@pytest.fixture()
def mock_data_read_service():
    return MagicMock()


@pytest.fixture()
def test_client(
    mock_analysis_service,
    mock_task_read_service,
    mock_rejection_read_service,
    mock_data_read_service,
):
    """DI override가 적용된 FastAPI TestClient (startup 이벤트 우회)"""
    app.dependency_overrides[get_analysis_service] = lambda: mock_analysis_service
    app.dependency_overrides[get_task_read_service] = lambda: mock_task_read_service
    app.dependency_overrides[get_rejection_read_service] = lambda: mock_rejection_read_service
    app.dependency_overrides[get_data_read_service] = lambda: mock_data_read_service

    with (
        patch("app.main.create_tables"),
        patch("app.adapter.outbound.mongodb.client.ensure_indexes"),
        TestClient(app, raise_server_exceptions=True) as client,
    ):
        yield client

    app.dependency_overrides.clear()


# === 도메인 객체 팩토리 ===

TASK_ID = "test-task-001"


def make_selection(
    video_id: int = 1,
    task_id: str = TASK_ID,
    recorded_at: datetime | None = None,
    temperature: float = 15.0,
    wiper_active: bool = False,
    wiper_level: int | None = None,
    headlights_on: bool = False,
    source_path: str = "/raw/video_001.mp4",
) -> Selection:
    return Selection(
        id=VideoId(video_id),
        task_id=task_id,
        recorded_at=recorded_at or datetime(2024, 6, 1, 12, 0, 0),
        temperature=Temperature.from_celsius(temperature),
        wiper=WiperState(active=wiper_active, level=wiper_level),
        headlights_on=headlights_on,
        source_path=SourcePath(source_path),
    )


def make_odd_tag(
    odd_id: int = 1,
    task_id: str = TASK_ID,
    video_id: int = 1,
    weather: Weather = Weather.SUNNY,
    time_of_day: TimeOfDay = TimeOfDay.DAY,
    road_surface: RoadSurface = RoadSurface.DRY,
) -> OddTag:
    return OddTag(
        id=odd_id,
        task_id=task_id,
        video_id=VideoId(video_id),
        weather=weather,
        time_of_day=time_of_day,
        road_surface=road_surface,
    )


def make_label(
    task_id: str = TASK_ID,
    video_id: int = 1,
    object_class: ObjectClass = ObjectClass.CAR,
    obj_count: int = 5,
    confidence: float = 0.92,
    labeled_at: datetime | None = None,
) -> Label:
    return Label(
        task_id=task_id,
        video_id=VideoId(video_id),
        object_class=object_class,
        obj_count=ObjectCount(obj_count),
        confidence=Confidence(confidence),
        labeled_at=labeled_at or datetime(2024, 6, 1, 13, 0, 0),
    )


def make_rejection(
    task_id: str = TASK_ID,
    stage: Stage = Stage.SELECTION,
    reason: RejectionReason = RejectionReason.INVALID_FORMAT,
    source_id: str = "row-001",
    field: str = "temperature",
    detail: str = "온도 값이 누락됨",
    created_at: datetime | None = None,
) -> Rejection:
    return Rejection(
        task_id=task_id,
        stage=stage,
        reason=reason,
        source_id=source_id,
        field=field,
        detail=detail,
        created_at=created_at or datetime(2024, 6, 1, 14, 0, 0),
    )
