import dataclasses
from datetime import datetime

import pytest

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
from app.domain.models import (
    AnalysisResult,
    AnalyzeTask,
    Label,
    OddTag,
    OutboxMessage,
    Rejection,
    Selection,
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


# === 테스트 픽스처 ===


def _make_selection(**overrides) -> Selection:
    defaults = dict(
        id=VideoId(1),
        task_id="task-001",
        recorded_at=datetime(2025, 1, 1),
        temperature=Temperature(celsius=20.0),
        wiper=WiperState(active=False),
        headlights_on=False,
        source_path=SourcePath("/raw/v.mp4"),
    )
    defaults.update(overrides)
    return Selection(**defaults)


def _make_odd_tag(**overrides) -> OddTag:
    defaults = dict(
        id=1,
        task_id="task-001",
        video_id=VideoId(1),
        weather=Weather.SUNNY,
        time_of_day=TimeOfDay.DAY,
        road_surface=RoadSurface.DRY,
    )
    defaults.update(overrides)
    return OddTag(**defaults)


def _make_label(**overrides) -> Label:
    defaults = dict(
        task_id="task-001",
        video_id=VideoId(1),
        object_class=ObjectClass.CAR,
        obj_count=ObjectCount(5),
        confidence=Confidence(0.95),
        labeled_at=datetime(2025, 1, 2),
    )
    defaults.update(overrides)
    return Label(**defaults)


# === Selection ===


class TestSelection:
    def test_frozen(self):
        sel = _make_selection()
        with pytest.raises(dataclasses.FrozenInstanceError):
            sel.task_id = "changed"  # type: ignore[misc]

    def test_is_night_driving(self):
        assert _make_selection(headlights_on=True).is_night_driving() is True
        assert _make_selection(headlights_on=False).is_night_driving() is False

    def test_adverse_weather_by_wiper(self):
        sel = _make_selection(wiper=WiperState(active=True, level=2))
        assert sel.is_adverse_weather_likely() is True

    def test_adverse_weather_by_temperature(self):
        sel = _make_selection(temperature=Temperature(celsius=-1.0))
        assert sel.is_adverse_weather_likely() is True

    def test_not_adverse_weather(self):
        sel = _make_selection(
            temperature=Temperature(celsius=20.0),
            wiper=WiperState(active=False),
        )
        assert sel.is_adverse_weather_likely() is False


# === OddTag ===


class TestOddTag:
    def test_valid_creation(self):
        tag = _make_odd_tag()
        assert tag.id == 1

    def test_zero_id_rejected(self):
        with pytest.raises(ValueError, match="양수"):
            _make_odd_tag(id=0)

    def test_negative_id_rejected(self):
        with pytest.raises(ValueError, match="양수"):
            _make_odd_tag(id=-1)

    def test_is_hazardous_icy(self):
        assert _make_odd_tag(road_surface=RoadSurface.ICY).is_hazardous() is True

    def test_is_hazardous_snowy_road(self):
        assert _make_odd_tag(road_surface=RoadSurface.SNOWY).is_hazardous() is True

    def test_is_hazardous_snowy_weather(self):
        assert _make_odd_tag(weather=Weather.SNOWY).is_hazardous() is True

    def test_is_hazardous_false(self):
        assert _make_odd_tag(
            road_surface=RoadSurface.DRY, weather=Weather.SUNNY,
        ).is_hazardous() is False

    def test_is_low_visibility_night(self):
        assert _make_odd_tag(time_of_day=TimeOfDay.NIGHT).is_low_visibility() is True

    def test_is_low_visibility_rainy(self):
        assert _make_odd_tag(weather=Weather.RAINY).is_low_visibility() is True

    def test_is_low_visibility_false(self):
        assert _make_odd_tag(
            time_of_day=TimeOfDay.DAY, weather=Weather.SUNNY,
        ).is_low_visibility() is False


# === Label ===


class TestLabel:
    def test_is_reliable_default(self):
        assert _make_label(confidence=Confidence(0.8)).is_reliable() is True
        assert _make_label(confidence=Confidence(0.79)).is_reliable() is False

    def test_is_reliable_custom_threshold(self):
        assert _make_label(confidence=Confidence(0.5)).is_reliable(threshold=0.5) is True

    def test_has_objects(self):
        assert _make_label(obj_count=ObjectCount(1)).has_objects() is True
        assert _make_label(obj_count=ObjectCount(0)).has_objects() is False


# === Rejection ===


class TestRejection:
    def test_valid_creation(self):
        r = Rejection(
            task_id="task-001",
            stage=Stage.SELECTION,
            reason=RejectionReason.INVALID_FORMAT,
            source_id="src-1",
            field="temperature",
            detail="범위 초과",
            created_at=datetime.now(),
        )
        assert r.source_id == "src-1"

    def test_empty_source_id_rejected(self):
        with pytest.raises(ValueError, match="source_id"):
            Rejection(
                task_id="task-001",
                stage=Stage.SELECTION,
                reason=RejectionReason.INVALID_FORMAT,
                source_id="",
                field="temperature",
                detail="범위 초과",
                created_at=datetime.now(),
            )

    def test_empty_detail_rejected(self):
        with pytest.raises(ValueError, match="detail"):
            Rejection(
                task_id="task-001",
                stage=Stage.SELECTION,
                reason=RejectionReason.INVALID_FORMAT,
                source_id="src-1",
                field="temperature",
                detail="",
                created_at=datetime.now(),
            )


# === AnalyzeTask ===


class TestAnalyzeTask:
    def test_create_new(self):
        task = AnalyzeTask.create_new("task-001", selection_count=10, odd_count=5, label_count=3)

        assert task.task_id == "task-001"
        assert task.status == TaskStatus.PENDING
        assert task.selection_progress.total == 10
        assert task.odd_tagging_progress.total == 5
        assert task.auto_labeling_progress.total == 3
        assert task.created_at is not None

    def test_start_processing(self):
        task = AnalyzeTask.create_new("t", 1, 1, 1)
        processing = task.start_processing()
        assert processing.status == TaskStatus.PROCESSING
        assert task.status == TaskStatus.PENDING  # 원본 불변

    def test_complete_with(self):
        result = AnalysisResult(
            selection=StageResult(10, 8, 2),
            odd_tagging=StageResult(5, 5, 0),
            auto_labeling=StageResult(3, 3, 0),
            fully_linked=3,
            partial=2,
        )
        task = AnalyzeTask.create_new("t", 1, 1, 1).start_processing()
        completed = task.complete_with(result)

        assert completed.status == TaskStatus.COMPLETED
        assert completed.result is result
        assert completed.completed_at is not None

    def test_fail_with(self):
        task = AnalyzeTask.create_new("t", 1, 1, 1).start_processing()
        failed = task.fail_with("timeout")

        assert failed.status == TaskStatus.FAILED
        assert failed.error == "timeout"
        assert failed.completed_at is not None

    def test_is_active(self):
        pending = AnalyzeTask.create_new("t", 1, 1, 1)
        processing = pending.start_processing()
        completed = processing.complete_with(
            AnalysisResult(
                StageResult(1, 1, 0), StageResult(1, 1, 0),
                StageResult(1, 1, 0), 1, 0,
            ),
        )
        failed = processing.fail_with("err")

        assert pending.is_active() is True
        assert processing.is_active() is True
        assert completed.is_active() is False
        assert failed.is_active() is False

    def test_should_run_phase_no_completed(self):
        task = AnalyzeTask.create_new("t", 1, 1, 1)
        assert task.should_run_phase(Stage.SELECTION) is True
        assert task.should_run_phase(Stage.ODD_TAGGING) is True
        assert task.should_run_phase(Stage.AUTO_LABELING) is True

    def test_should_run_phase_resume_after_selection(self):
        task = AnalyzeTask.create_new("t", 1, 1, 1).with_completed_phase(Stage.SELECTION)
        assert task.should_run_phase(Stage.SELECTION) is False
        assert task.should_run_phase(Stage.ODD_TAGGING) is True
        assert task.should_run_phase(Stage.AUTO_LABELING) is True

    def test_should_run_phase_resume_after_odd_tagging(self):
        task = AnalyzeTask.create_new("t", 1, 1, 1).with_completed_phase(Stage.ODD_TAGGING)
        assert task.should_run_phase(Stage.SELECTION) is False
        assert task.should_run_phase(Stage.ODD_TAGGING) is False
        assert task.should_run_phase(Stage.AUTO_LABELING) is True

    def test_with_progress(self):
        task = AnalyzeTask.create_new("t", 10, 5, 3)
        new_progress = StageProgress(total=10, processed=5, rejected=1)
        updated = task.with_progress(Stage.SELECTION, new_progress)

        assert updated.selection_progress == new_progress
        assert task.selection_progress != new_progress  # 원본 불변

    def test_with_completed_phase(self):
        task = AnalyzeTask.create_new("t", 1, 1, 1)
        updated = task.with_completed_phase(Stage.ODD_TAGGING)
        assert updated.last_completed_phase == Stage.ODD_TAGGING
        assert task.last_completed_phase is None  # 원본 불변

    def test_get_progress_for(self):
        task = AnalyzeTask.create_new("t", 10, 5, 3)
        assert task.get_progress_for(Stage.SELECTION).total == 10
        assert task.get_progress_for(Stage.ODD_TAGGING).total == 5
        assert task.get_progress_for(Stage.AUTO_LABELING).total == 3

    def test_상태_전이_체인_정상_완료(self):
        """PENDING → PROCESSING → COMPLETED 전체 체인 + 원본 불변 확인"""
        # Arrange
        original = AnalyzeTask.create_new("t", 10, 5, 3)

        # Act: 전이 체인
        processing = original.start_processing()
        result = AnalysisResult(
            selection=StageResult(10, 8, 2),
            odd_tagging=StageResult(5, 5, 0),
            auto_labeling=StageResult(3, 3, 0),
            fully_linked=3,
            partial=2,
        )
        completed = processing.complete_with(result)

        # Assert: 각 단계 상태 확인
        assert original.status == TaskStatus.PENDING
        assert processing.status == TaskStatus.PROCESSING
        assert completed.status == TaskStatus.COMPLETED
        assert completed.result is result
        assert completed.completed_at is not None

        # Assert: 원본 불변
        assert original.status == TaskStatus.PENDING
        assert original.result is None
        assert original.completed_at is None

    def test_상태_전이_체인_실패(self):
        """PENDING → PROCESSING → FAILED 전체 체인 + 원본 불변 확인"""
        # Arrange
        original = AnalyzeTask.create_new("t", 10, 5, 3)

        # Act: 전이 체인
        processing = original.start_processing()
        failed = processing.fail_with("파이프라인 타임아웃")

        # Assert: 각 단계 상태 확인
        assert original.status == TaskStatus.PENDING
        assert processing.status == TaskStatus.PROCESSING
        assert failed.status == TaskStatus.FAILED
        assert failed.error == "파이프라인 타임아웃"
        assert failed.completed_at is not None

        # Assert: 원본 불변
        assert original.status == TaskStatus.PENDING
        assert original.error is None


# === OutboxMessage ===


class TestOutboxMessage:
    def test_create_analyze_event(self):
        msg = OutboxMessage.create_analyze_event("msg-001", "task-001")

        assert msg.message_id == "msg-001"
        assert msg.message_type == "ANALYZE"
        assert msg.payload == {"task_id": "task-001"}
        assert msg.status == OutboxStatus.PENDING
        assert msg.retry_count == 0
        assert msg.created_at is not None

    def test_mark_processing(self):
        msg = OutboxMessage.create_analyze_event("m", "t")
        processing = msg.mark_processing()
        assert processing.status == OutboxStatus.PROCESSING
        assert msg.status == OutboxStatus.PENDING  # 원본 불변

    def test_mark_published(self):
        msg = OutboxMessage.create_analyze_event("m", "t").mark_processing()
        published = msg.mark_published()
        assert published.status == OutboxStatus.PUBLISHED

    def test_mark_failed(self):
        msg = OutboxMessage.create_analyze_event("m", "t").mark_processing()
        failed = msg.mark_failed()
        assert failed.status == OutboxStatus.FAILED

    def test_back_to_pending(self):
        msg = OutboxMessage.create_analyze_event("m", "t").mark_processing()
        pending = msg.back_to_pending()
        assert pending.status == OutboxStatus.PENDING

    def test_is_retriable(self):
        msg = OutboxMessage.create_analyze_event("m", "t")
        assert msg.is_retriable() is True

        exhausted = OutboxMessage(
            message_id="m", message_type="ANALYZE",
            payload={}, retry_count=3, max_retries=3,
        )
        assert exhausted.is_retriable() is False

    def test_with_retry_incremented(self):
        msg = OutboxMessage.create_analyze_event("m", "t")
        retried = msg.with_retry_incremented()
        assert retried.retry_count == 1
        assert msg.retry_count == 0  # 원본 불변

    def test_state_transition_chain(self):
        """전체 상태 전이 체인: PENDING → PROCESSING → PUBLISHED"""
        msg = OutboxMessage.create_analyze_event("m", "t")
        assert msg.status == OutboxStatus.PENDING

        msg = msg.mark_processing()
        assert msg.status == OutboxStatus.PROCESSING

        msg = msg.mark_published()
        assert msg.status == OutboxStatus.PUBLISHED

    def test_retry_chain(self):
        """재시도 체인: PROCESSING → PENDING (back) → retry++"""
        msg = OutboxMessage.create_analyze_event("m", "t").mark_processing()
        msg = msg.back_to_pending().with_retry_incremented()
        assert msg.status == OutboxStatus.PENDING
        assert msg.retry_count == 1

    def test_재시도_최대_횟수까지_is_retriable_변화(self):
        """retry_increment를 max_retries까지 반복하면 is_retriable이 False로 전환된다"""
        msg = OutboxMessage.create_analyze_event("m", "t")
        assert msg.max_retries == 3

        # 1회 재시도
        msg = msg.with_retry_incremented()
        assert msg.retry_count == 1
        assert msg.is_retriable() is True

        # 2회 재시도
        msg = msg.with_retry_incremented()
        assert msg.retry_count == 2
        assert msg.is_retriable() is True

        # 3회 재시도 (max_retries 도달)
        msg = msg.with_retry_incremented()
        assert msg.retry_count == 3
        assert msg.is_retriable() is False


# === AnalysisResult ===


class TestAnalysisResult:
    def test_frozen(self):
        result = AnalysisResult(
            selection=StageResult(10, 8, 2),
            odd_tagging=StageResult(5, 5, 0),
            auto_labeling=StageResult(3, 3, 0),
            fully_linked=3,
            partial=2,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.fully_linked = 99  # type: ignore[misc]

    def test_values(self):
        result = AnalysisResult(
            selection=StageResult(10, 8, 2),
            odd_tagging=StageResult(5, 5, 0),
            auto_labeling=StageResult(3, 3, 0),
            fully_linked=3,
            partial=2,
        )
        assert result.selection.total == 10
        assert result.fully_linked == 3
        assert result.partial == 2
