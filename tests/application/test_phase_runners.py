"""PhaseRunner 단위 테스트

테스트 대상: PhaseRunnerProvider, SelectionPhaseRunner (주), OddTagPhaseRunner/LabelPhaseRunner (속성만)
전략: Mock(spec=ABC)으로 Repository 의존성 주입, Arrange-Act-Assert 패턴
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.application.phase_runners import (
    LabelPhaseRunner,
    OddTagPhaseRunner,
    PhaseRunner,
    PhaseRunnerProvider,
    SelectionPhaseRunner,
)
from app.domain.enums import RejectionReason, Stage, TaskStatus
from app.domain.models import AnalyzeTask, Rejection, Selection
from app.domain.ports import (
    LabelRepository,
    OddTagRepository,
    RawDataRepository,
    RejectionRepository,
    SelectionRepository,
    TaskRepository,
)
from app.domain.value_objects import SourcePath, StageProgress, Temperature, VideoId, WiperState


# === Fixture ===


@pytest.fixture
def raw_data_repo():
    return MagicMock(spec=RawDataRepository)


@pytest.fixture
def task_repo():
    return MagicMock(spec=TaskRepository)


@pytest.fixture
def rejection_repo():
    return MagicMock(spec=RejectionRepository)


@pytest.fixture
def selection_repo():
    return MagicMock(spec=SelectionRepository)


@pytest.fixture
def odd_tag_repo():
    return MagicMock(spec=OddTagRepository)


@pytest.fixture
def label_repo():
    return MagicMock(spec=LabelRepository)


@pytest.fixture
def selection_runner(raw_data_repo, task_repo, rejection_repo, selection_repo):
    return SelectionPhaseRunner(
        raw_data_repo=raw_data_repo,
        task_repo=task_repo,
        rejection_repo=rejection_repo,
        selection_repo=selection_repo,
        chunk_size=3,
    )


def _make_task(
    task_id="task-1",
    status=TaskStatus.PROCESSING,
    sel_total=10,
    odd_total=5,
    label_total=5,
) -> AnalyzeTask:
    return AnalyzeTask(
        task_id=task_id,
        status=status,
        selection_progress=StageProgress(total=sel_total),
        odd_tagging_progress=StageProgress(total=odd_total),
        auto_labeling_progress=StageProgress(total=label_total),
    )


def _make_v1_row(vid: int = 1, temp: float = 25.0) -> dict:
    """유효한 V1 Selection 원본 데이터를 생성한다."""
    return {
        "id": vid,
        "recordedAt": "2026-01-01T12:00:00",
        "temperature": temp,
        "isWiperOn": False,
        "headlightsOn": True,
        "sourcePath": f"/raw/video_{vid}.mp4",
    }


def _make_selection(vid: int = 1) -> Selection:
    """테스트용 Selection 도메인 모델을 생성한다."""
    return Selection(
        id=VideoId(vid),
        task_id="task-1",
        recorded_at=datetime(2026, 1, 1, 12, 0),
        temperature=Temperature.from_celsius(25.0),
        wiper=WiperState(active=False),
        headlights_on=True,
        source_path=SourcePath(f"/raw/video_{vid}.mp4"),
    )


def _make_rejection(task_id: str = "task-1", stage: Stage = Stage.SELECTION) -> Rejection:
    return Rejection(
        task_id=task_id,
        stage=stage,
        reason=RejectionReason.INVALID_FORMAT,
        source_id="1",
        field="temperature",
        detail="temperature 파싱 불가",
        created_at=datetime.now(),
    )


# === PhaseRunnerProvider 테스트 ===


class TestPhaseRunnerProvider:

    def test_등록된_stage_올바른_runner_반환(self, selection_runner):
        """get()으로 등록된 Stage를 조회하면 올바른 runner가 반환된다"""
        provider = PhaseRunnerProvider()
        provider.register(Stage.SELECTION, selection_runner)

        result = provider.get(Stage.SELECTION)

        assert result is selection_runner

    def test_미등록_stage_ValueError(self):
        """get()으로 미등록 Stage를 조회하면 ValueError가 발생한다"""
        provider = PhaseRunnerProvider()

        with pytest.raises(ValueError, match="등록되지 않은 Phase"):
            provider.get(Stage.SELECTION)

    def test_여러_stage_등록_각각_올바른_runner_반환(
        self, raw_data_repo, task_repo, rejection_repo, selection_repo, odd_tag_repo, label_repo
    ):
        """여러 Stage를 등록하면 각각 올바른 runner를 반환한다"""
        provider = PhaseRunnerProvider()
        sel_runner = SelectionPhaseRunner(raw_data_repo, task_repo, rejection_repo, selection_repo)
        odd_runner = OddTagPhaseRunner(raw_data_repo, task_repo, rejection_repo, odd_tag_repo)
        label_runner = LabelPhaseRunner(raw_data_repo, task_repo, rejection_repo, label_repo)

        provider.register(Stage.SELECTION, sel_runner)
        provider.register(Stage.ODD_TAGGING, odd_runner)
        provider.register(Stage.AUTO_LABELING, label_runner)

        assert provider.get(Stage.SELECTION) is sel_runner
        assert provider.get(Stage.ODD_TAGGING) is odd_runner
        assert provider.get(Stage.AUTO_LABELING) is label_runner


# === Runner stage/source 속성 테스트 ===


class TestPhaseRunnerProperties:

    def test_selection_runner_stage_SELECTION(self, selection_runner):
        assert selection_runner.stage == Stage.SELECTION

    def test_selection_runner_source_selections(self, selection_runner):
        assert selection_runner.source == "selections"

    def test_odd_tag_runner_stage_ODD_TAGGING(self, raw_data_repo, task_repo, rejection_repo, odd_tag_repo):
        runner = OddTagPhaseRunner(raw_data_repo, task_repo, rejection_repo, odd_tag_repo)
        assert runner.stage == Stage.ODD_TAGGING

    def test_odd_tag_runner_source_odds(self, raw_data_repo, task_repo, rejection_repo, odd_tag_repo):
        runner = OddTagPhaseRunner(raw_data_repo, task_repo, rejection_repo, odd_tag_repo)
        assert runner.source == "odds"

    def test_label_runner_stage_AUTO_LABELING(self, raw_data_repo, task_repo, rejection_repo, label_repo):
        runner = LabelPhaseRunner(raw_data_repo, task_repo, rejection_repo, label_repo)
        assert runner.stage == Stage.AUTO_LABELING

    def test_label_runner_source_labels(self, raw_data_repo, task_repo, rejection_repo, label_repo):
        runner = LabelPhaseRunner(raw_data_repo, task_repo, rejection_repo, label_repo)
        assert runner.source == "labels"


# === SelectionPhaseRunner.run() 테스트 ===


class TestSelectionPhaseRunnerRun:

    def test_정상_스트리밍_처리(self, selection_runner, raw_data_repo, task_repo, selection_repo, rejection_repo):
        """정상 흐름: 스트리밍 데이터 -> 정제 -> 적재 -> StageResult 반환"""
        task = _make_task(sel_total=3)
        rows = [_make_v1_row(vid=i) for i in range(1, 4)]
        raw_data_repo.find_by_task_and_source.return_value = iter(rows)
        selection_repo.save_all.return_value = 3  # 3건 모두 적재

        result, updated_task = selection_runner.run(task, "task-1")

        assert result.total == 3
        assert result.loaded == 3
        assert result.rejected == 0
        selection_repo.save_all.assert_called_once()
        rejection_repo.save_all.assert_not_called()
        task_repo.save.assert_called_once()

    def test_빈_데이터_처리(self, selection_runner, raw_data_repo, task_repo, selection_repo, rejection_repo):
        """빈 데이터: rows=[] -> loaded_count=0, rejected_count=0"""
        task = _make_task(sel_total=0)
        raw_data_repo.find_by_task_and_source.return_value = iter([])

        result, updated_task = selection_runner.run(task, "task-1")

        assert result.total == 0
        assert result.loaded == 0
        assert result.rejected == 0
        selection_repo.save_all.assert_not_called()
        rejection_repo.save_all.assert_not_called()
        task_repo.save.assert_called_once()

    def test_전체_실패_모든_row_정제_실패(self, selection_runner, raw_data_repo, task_repo, selection_repo, rejection_repo):
        """전체 실패: 모든 row가 정제 실패하면 rejected_count = len(rows)"""
        task = _make_task(sel_total=2)
        # 유효하지 않은 데이터 (temperature/sensor 없음 -> UNKNOWN_SCHEMA)
        invalid_rows = [
            {"id": 1, "recordedAt": "2026-01-01T12:00:00"},
            {"id": 2, "recordedAt": "2026-01-01T12:00:00"},
        ]
        raw_data_repo.find_by_task_and_source.return_value = iter(invalid_rows)

        result, updated_task = selection_runner.run(task, "task-1")

        assert result.loaded == 0
        assert result.rejected > 0
        selection_repo.save_all.assert_not_called()
        rejection_repo.save_all.assert_called()

    def test_혼합_일부_성공_일부_실패(self, selection_runner, raw_data_repo, task_repo, selection_repo, rejection_repo):
        """혼합: 일부 성공 + 일부 실패 (valid + rejection 분리)"""
        task = _make_task(sel_total=3)
        rows = [
            _make_v1_row(vid=1),                             # 성공
            {"id": 2, "recordedAt": "2026-01-01T12:00:00"},  # 실패 (UNKNOWN_SCHEMA)
            _make_v1_row(vid=3),                             # 성공
        ]
        raw_data_repo.find_by_task_and_source.return_value = iter(rows)
        selection_repo.save_all.return_value = 2  # 2건 적재

        result, updated_task = selection_runner.run(task, "task-1")

        assert result.loaded == 2
        assert result.rejected > 0
        selection_repo.save_all.assert_called_once()
        rejection_repo.save_all.assert_called()

    def test_청크_분할_처리(self, selection_runner, raw_data_repo, task_repo, selection_repo, rejection_repo):
        """chunk_size=3일 때 5건의 데이터가 2개 청크로 분할 처리된다"""
        task = _make_task(sel_total=5)
        rows = [_make_v1_row(vid=i) for i in range(1, 6)]
        raw_data_repo.find_by_task_and_source.return_value = iter(rows)
        selection_repo.save_all.side_effect = [3, 2]  # 첫 청크 3건, 둘째 청크 2건

        result, updated_task = selection_runner.run(task, "task-1")

        assert result.loaded == 5
        assert result.rejected == 0
        assert selection_repo.save_all.call_count == 2


# === INSERT IGNORE 중복 처리 테스트 ===


class TestInsertIgnoreDuplicate:

    def test_중복_0건_duplicate_rejection_없음(self, selection_runner, raw_data_repo, task_repo, selection_repo, rejection_repo):
        """중복 0건: inserted == len(valid) -> duplicate rejections 없음"""
        task = _make_task(sel_total=3)
        rows = [_make_v1_row(vid=i) for i in range(1, 4)]
        raw_data_repo.find_by_task_and_source.return_value = iter(rows)
        selection_repo.save_all.return_value = 3  # 전부 적재됨

        result, _ = selection_runner.run(task, "task-1")

        assert result.loaded == 3
        assert result.rejected == 0
        rejection_repo.save_all.assert_not_called()

    def test_부분_중복_duplicate_rejection_생성(self, selection_runner, raw_data_repo, task_repo, selection_repo, rejection_repo):
        """부분 중복: inserted < len(valid) -> duplicate rejection 생성"""
        task = _make_task(sel_total=3)
        rows = [_make_v1_row(vid=i) for i in range(1, 4)]
        raw_data_repo.find_by_task_and_source.return_value = iter(rows)
        selection_repo.save_all.return_value = 2  # 3건 중 2건만 적재 (1건 중복)

        result, _ = selection_runner.run(task, "task-1")

        assert result.loaded == 2
        assert result.rejected > 0
        rejection_repo.save_all.assert_called_once()
        saved_rejections = rejection_repo.save_all.call_args[0][0]
        # duplicate rejection이 포함되어 있어야 한다
        dup_rejections = [r for r in saved_rejections if "UNIQUE 제약 위반" in r.detail]
        assert len(dup_rejections) == 1

    def test_전체_중복_inserted_0(self, selection_runner, raw_data_repo, task_repo, selection_repo, rejection_repo):
        """전체 중복: inserted == 0 -> duplicate_count == len(valid)"""
        task = _make_task(sel_total=3)
        rows = [_make_v1_row(vid=i) for i in range(1, 4)]
        raw_data_repo.find_by_task_and_source.return_value = iter(rows)
        selection_repo.save_all.return_value = 0  # 전부 중복

        result, _ = selection_runner.run(task, "task-1")

        assert result.loaded == 0
        assert result.rejected > 0
        rejection_repo.save_all.assert_called_once()
        saved_rejections = rejection_repo.save_all.call_args[0][0]
        dup_rejections = [r for r in saved_rejections if "UNIQUE 제약 위반" in r.detail]
        assert len(dup_rejections) == 1
        assert "3건 무시됨" in dup_rejections[0].detail


# === _build_duplicate_rejections 테스트 ===


class TestBuildDuplicateRejections:

    def test_ODD_TAGGING_stage_DUPLICATE_TAGGING_reason(self, raw_data_repo, task_repo, rejection_repo, odd_tag_repo):
        """ODD_TAGGING Stage -> DUPLICATE_TAGGING reason"""
        runner = OddTagPhaseRunner(raw_data_repo, task_repo, rejection_repo, odd_tag_repo)

        rejections = runner._build_duplicate_rejections("task-1", 5)

        assert len(rejections) == 1
        assert rejections[0].reason == RejectionReason.DUPLICATE_TAGGING
        assert rejections[0].stage == Stage.ODD_TAGGING
        assert "5건 무시됨" in rejections[0].detail

    def test_AUTO_LABELING_stage_DUPLICATE_LABEL_reason(self, raw_data_repo, task_repo, rejection_repo, label_repo):
        """AUTO_LABELING Stage -> DUPLICATE_LABEL reason"""
        runner = LabelPhaseRunner(raw_data_repo, task_repo, rejection_repo, label_repo)

        rejections = runner._build_duplicate_rejections("task-1", 3)

        assert len(rejections) == 1
        assert rejections[0].reason == RejectionReason.DUPLICATE_LABEL
        assert rejections[0].stage == Stage.AUTO_LABELING
        assert "3건 무시됨" in rejections[0].detail

    def test_SELECTION_stage_DUPLICATE_LABEL_reason(self, selection_runner):
        """SELECTION Stage -> DUPLICATE_LABEL reason (SELECTION은 ODD_TAGGING이 아니므로)"""
        rejections = selection_runner._build_duplicate_rejections("task-1", 2)

        assert len(rejections) == 1
        assert rejections[0].reason == RejectionReason.DUPLICATE_LABEL
        assert "2건 무시됨" in rejections[0].detail


# === _refine_chunk 테스트 ===


class TestRefineChunk:

    def test_result가_list_Rejection이면_rejections_extend(self, selection_runner):
        """_refine_single이 list[Rejection]을 반환하면 rejections.extend()"""
        rejection1 = _make_rejection()
        rejection2 = _make_rejection()

        with patch.object(selection_runner, "_refine_single", return_value=[rejection1, rejection2]):
            valid, rejections = selection_runner._refine_chunk("task-1", [{"id": 1}], set())

        assert len(valid) == 0
        assert len(rejections) == 2
        assert rejection1 in rejections
        assert rejection2 in rejections

    def test_result가_단일_Rejection이면_rejections_append(self, selection_runner):
        """_refine_single이 단일 Rejection을 반환하면 rejections.append()"""
        rejection = _make_rejection()

        with patch.object(selection_runner, "_refine_single", return_value=rejection):
            valid, rejections = selection_runner._refine_chunk("task-1", [{"id": 1}], set())

        assert len(valid) == 0
        assert len(rejections) == 1
        assert rejections[0] is rejection

    def test_result가_도메인_모델이면_valid_append(self, selection_runner):
        """_refine_single이 도메인 모델을 반환하면 valid.append()"""
        selection = _make_selection(vid=1)

        with patch.object(selection_runner, "_refine_single", return_value=selection):
            valid, rejections = selection_runner._refine_chunk("task-1", [{"id": 1}], set())

        assert len(valid) == 1
        assert valid[0] is selection
        assert len(rejections) == 0

    def test_혼합_결과_valid와_rejection_분리(self, selection_runner):
        """여러 row에서 성공/실패가 섞여 있으면 각각 분리된다"""
        selection = _make_selection(vid=1)
        rejection = _make_rejection()

        results = [selection, rejection, [_make_rejection(), _make_rejection()]]

        with patch.object(selection_runner, "_refine_single", side_effect=results):
            valid, rejections = selection_runner._refine_chunk(
                "task-1", [{"id": 1}, {"id": 2}, {"id": 3}], set()
            )

        assert len(valid) == 1
        assert len(rejections) == 3  # 1 (append) + 2 (extend)


# === 진행률 갱신 테스트 ===


class TestProgressUpdate:

    def test_run_완료후_with_progress_호출(self, selection_runner, raw_data_repo, task_repo, selection_repo):
        """run() 완료 후 task.with_progress()가 호출되어 진행률이 갱신된다"""
        task = _make_task(sel_total=3)
        rows = [_make_v1_row(vid=i) for i in range(1, 4)]
        raw_data_repo.find_by_task_and_source.return_value = iter(rows)
        selection_repo.save_all.return_value = 3

        result, updated_task = selection_runner.run(task, "task-1")

        # 갱신된 task의 selection_progress 확인
        progress = updated_task.selection_progress
        assert progress.processed == 3
        assert progress.rejected == 0
        assert progress.total == 3

    def test_run_완료후_with_completed_phase_호출(self, selection_runner, raw_data_repo, task_repo, selection_repo):
        """run() 완료 후 task.with_completed_phase()가 호출된다"""
        task = _make_task(sel_total=2)
        rows = [_make_v1_row(vid=i) for i in range(1, 3)]
        raw_data_repo.find_by_task_and_source.return_value = iter(rows)
        selection_repo.save_all.return_value = 2

        _, updated_task = selection_runner.run(task, "task-1")

        assert updated_task.last_completed_phase == Stage.SELECTION

    def test_run_완료후_task_repo_save_호출(self, selection_runner, raw_data_repo, task_repo, selection_repo):
        """run() 완료 후 task_repo.save()가 호출된다"""
        task = _make_task(sel_total=1)
        rows = [_make_v1_row(vid=1)]
        raw_data_repo.find_by_task_and_source.return_value = iter(rows)
        selection_repo.save_all.return_value = 1

        selection_runner.run(task, "task-1")

        task_repo.save.assert_called_once()
        saved_task = task_repo.save.call_args[0][0]
        assert saved_task.last_completed_phase == Stage.SELECTION
        assert saved_task.selection_progress.processed == 1

    def test_실패_포함_진행률_갱신(self, selection_runner, raw_data_repo, task_repo, selection_repo, rejection_repo):
        """일부 실패 시 rejected 카운트가 진행률에 반영된다"""
        task = _make_task(sel_total=3)
        rows = [
            _make_v1_row(vid=1),
            {"id": 2, "recordedAt": "2026-01-01T12:00:00"},  # 실패
            _make_v1_row(vid=3),
        ]
        raw_data_repo.find_by_task_and_source.return_value = iter(rows)
        selection_repo.save_all.return_value = 2

        result, updated_task = selection_runner.run(task, "task-1")

        progress = updated_task.selection_progress
        assert progress.processed == 2
        assert progress.rejected > 0
        assert progress.total == 3
