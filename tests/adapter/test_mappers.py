"""Mapper 왕복(roundtrip) 검증 테스트"""

from datetime import datetime

from app.adapter.inbound.rest.mappers import DataSearchCriteriaMapper, RejectionCriteriaMapper
from app.adapter.inbound.rest.schemas import DataSearchRequest, RejectionSearchRequest
from app.adapter.outbound.mysql.mappers import (
    LabelMapper,
    OddTagMapper,
    RejectionMapper,
    SelectionMapper,
)
from app.domain.enums import (
    ObjectClass,
    RejectionReason,
    RoadSurface,
    Stage,
    TimeOfDay,
    Weather,
)
from tests.adapter.conftest import make_label, make_odd_tag, make_rejection, make_selection

# === MySQL Mapper 왕복 검증 ===


class TestSelectionMapper:
    def test_roundtrip(self):
        domain = make_selection(video_id=42, task_id="task-sel-001", temperature=22.5, headlights_on=True)

        entity = SelectionMapper.to_entity(domain)
        restored = SelectionMapper.to_domain(entity)

        assert restored.id.value == 42
        assert restored.task_id == "task-sel-001"
        assert restored.temperature.celsius == 22.5
        assert restored.headlights_on is True
        assert restored.source_path.value == domain.source_path.value
        assert restored.recorded_at == domain.recorded_at
        assert restored.wiper.active == domain.wiper.active

    def test_to_dict_matches_entity(self):
        domain = make_selection(video_id=10)

        d = SelectionMapper.to_dict(domain)
        entity = SelectionMapper.to_entity(domain)

        assert d["id"] == entity.id
        assert d["task_id"] == entity.task_id
        assert d["temperature_celsius"] == entity.temperature_celsius
        assert d["source_path"] == entity.source_path


class TestOddTagMapper:
    def test_roundtrip(self):
        domain = make_odd_tag(
            odd_id=7,
            task_id="task-odd-001",
            video_id=42,
            weather=Weather.RAINY,
            time_of_day=TimeOfDay.NIGHT,
            road_surface=RoadSurface.WET,
        )

        entity = OddTagMapper.to_entity(domain)
        restored = OddTagMapper.to_domain(entity)

        assert restored.id == 7
        assert restored.task_id == "task-odd-001"
        assert restored.video_id.value == 42
        assert restored.weather == Weather.RAINY
        assert restored.time_of_day == TimeOfDay.NIGHT
        assert restored.road_surface == RoadSurface.WET


class TestLabelMapper:
    def test_roundtrip(self):
        labeled_at = datetime(2024, 7, 15, 10, 30, 0)
        domain = make_label(
            task_id="task-lbl-001",
            video_id=99,
            object_class=ObjectClass.PEDESTRIAN,
            obj_count=3,
            confidence=0.87,
            labeled_at=labeled_at,
        )

        entity = LabelMapper.to_entity(domain)
        restored = LabelMapper.to_domain(entity)

        assert restored.task_id == "task-lbl-001"
        assert restored.video_id.value == 99
        assert restored.object_class == ObjectClass.PEDESTRIAN
        assert restored.obj_count.value == 3
        assert restored.confidence.value == 0.87
        assert restored.labeled_at == labeled_at


class TestRejectionMapper:
    def test_roundtrip(self):
        created = datetime(2024, 8, 1, 9, 0, 0)
        domain = make_rejection(
            task_id="task-rej-001",
            stage=Stage.ODD_TAGGING,
            reason=RejectionReason.DUPLICATE_TAGGING,
            source_id="odd-row-55",
            field="weather",
            detail="중복 태깅 발견",
            created_at=created,
        )

        entity = RejectionMapper.to_entity(domain)
        restored = RejectionMapper.to_domain(entity)

        assert restored.task_id == "task-rej-001"
        assert restored.stage == Stage.ODD_TAGGING
        assert restored.reason == RejectionReason.DUPLICATE_TAGGING
        assert restored.source_id == "odd-row-55"
        assert restored.field == "weather"
        assert restored.detail == "중복 태깅 발견"
        assert restored.created_at == created


# === REST Mapper 변환 검증 ===


class TestRejectionCriteriaMapper:
    def test_full_criteria(self):
        request = RejectionSearchRequest(
            task_id="task-001",
            stage=Stage.SELECTION,
            reason=RejectionReason.INVALID_FORMAT,
            source_id="src-001",
            field="temperature",
            page=2,
            size=50,
        )

        criteria = RejectionCriteriaMapper.to_domain(request)

        assert criteria.task_id == "task-001"
        assert criteria.stage == Stage.SELECTION
        assert criteria.reason == RejectionReason.INVALID_FORMAT
        assert criteria.source_id == "src-001"
        assert criteria.field == "temperature"
        assert criteria.page == 2
        assert criteria.size == 50

    def test_minimal_criteria(self):
        request = RejectionSearchRequest()

        criteria = RejectionCriteriaMapper.to_domain(request)

        assert criteria.task_id is None
        assert criteria.stage is None
        assert criteria.reason is None
        assert criteria.page == 1
        assert criteria.size == 20


class TestDataSearchCriteriaMapper:
    def test_full_criteria(self):
        request = DataSearchRequest(
            task_id="task-002",
            recorded_at_from=datetime(2024, 1, 1),
            recorded_at_to=datetime(2024, 12, 31),
            min_temperature=-10.0,
            max_temperature=40.0,
            headlights_on=True,
            weather=Weather.RAINY,
            time_of_day=TimeOfDay.NIGHT,
            road_surface=RoadSurface.WET,
            object_class=ObjectClass.CAR,
            min_obj_count=3,
            min_confidence=0.8,
            page=3,
            size=10,
        )

        criteria = DataSearchCriteriaMapper.to_domain(request)

        assert criteria.task_id == "task-002"
        assert criteria.recorded_at_from == datetime(2024, 1, 1)
        assert criteria.recorded_at_to == datetime(2024, 12, 31)
        assert criteria.min_temperature == -10.0
        assert criteria.max_temperature == 40.0
        assert criteria.headlights_on is True
        assert criteria.weather == Weather.RAINY
        assert criteria.time_of_day == TimeOfDay.NIGHT
        assert criteria.road_surface == RoadSurface.WET
        assert criteria.object_class == ObjectClass.CAR
        assert criteria.min_obj_count == 3
        assert criteria.min_confidence == 0.8
        assert criteria.page == 3
        assert criteria.size == 10

    def test_minimal_criteria(self):
        request = DataSearchRequest()

        criteria = DataSearchCriteriaMapper.to_domain(request)

        assert criteria.task_id is None
        assert criteria.weather is None
        assert criteria.object_class is None
        assert criteria.page == 1
        assert criteria.size == 20
