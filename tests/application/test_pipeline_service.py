from unittest.mock import MagicMock

import pytest

from app.application.phase_runners import PhaseRunnerProvider
from app.application.pipeline_service import PipelineService
from app.domain.enums import Stage, TaskStatus
from app.domain.models import AnalyzeTask
from app.domain.ports import (
    LabelRepository,
    OddTagRepository,
    SelectionRepository,
    TaskRepository,
)
from app.domain.value_objects import StageProgress, StageResult


@pytest.fixture
def task_repo():
    return MagicMock(spec=TaskRepository)


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
def phase_provider():
    return MagicMock(spec=PhaseRunnerProvider)


@pytest.fixture
def service(task_repo, selection_repo, odd_tag_repo, label_repo, phase_provider):
    return PipelineService(
        task_repo=task_repo,
        selection_repo=selection_repo,
        odd_tag_repo=odd_tag_repo,
        label_repo=label_repo,
        phase_runner_provider=phase_provider,
    )


def _make_task(
    task_id="task-1",
    status=TaskStatus.PENDING,
    last_completed_phase=None,
    sel_total=100,
    odd_total=80,
    label_total=60,
) -> AnalyzeTask:
    return AnalyzeTask(
        task_id=task_id,
        status=status,
        selection_progress=StageProgress(total=sel_total),
        odd_tagging_progress=StageProgress(total=odd_total),
        auto_labeling_progress=StageProgress(total=label_total),
        last_completed_phase=last_completed_phase,
    )


def _mock_runner(result: StageResult):
    """run() 호출 시 (result, updated_task)를 반환하는 mock runner"""
    runner = MagicMock()

    def run_side_effect(task, task_id, valid_selection_ids=None):
        updated = task.with_completed_phase(runner._stage)
        return result, updated

    runner.run.side_effect = run_side_effect
    return runner


class TestPipelineServiceExecute:

    def test_정상_실행_전체_흐름(self, service, task_repo, selection_repo, odd_tag_repo, label_repo, phase_provider):
        task = _make_task()
        task_repo.find_by_id.return_value = task

        sel_result = StageResult(total=100, loaded=90, rejected=10)
        odd_result = StageResult(total=80, loaded=70, rejected=10)
        label_result = StageResult(total=60, loaded=55, rejected=5)

        sel_runner = MagicMock()
        odd_runner = MagicMock()
        label_runner = MagicMock()

        def make_run(stage, result):
            def run(t, tid, vids=None):
                return result, t.with_completed_phase(stage)
            return run

        sel_runner.run.side_effect = make_run(Stage.SELECTION, sel_result)
        odd_runner.run.side_effect = make_run(Stage.ODD_TAGGING, odd_result)
        label_runner.run.side_effect = make_run(Stage.AUTO_LABELING, label_result)

        phase_provider.get.side_effect = lambda s: {
            Stage.SELECTION: sel_runner,
            Stage.ODD_TAGGING: odd_runner,
            Stage.AUTO_LABELING: label_runner,
        }[s]

        selection_repo.find_all_ids_by_task.return_value = {1, 2, 3}
        odd_tag_repo.find_all_video_ids_by_task.return_value = {1, 2}
        label_repo.find_all_video_ids_by_task.return_value = {1, 2}

        service.execute("task-1")

        # start_processing → save 호출 확인
        assert task_repo.save.call_count >= 2
        first_save = task_repo.save.call_args_list[0][0][0]
        assert first_save.status == TaskStatus.PROCESSING

        # complete_with → save 호출 확인
        last_save = task_repo.save.call_args_list[-1][0][0]
        assert last_save.status == TaskStatus.COMPLETED
        assert last_save.result is not None

    def test_실패시_fail_with_save(self, service, task_repo, phase_provider, selection_repo):
        task = _make_task()
        task_repo.find_by_id.return_value = task

        sel_runner = MagicMock()
        sel_runner.run.side_effect = RuntimeError("파싱 에러")
        phase_provider.get.return_value = sel_runner

        with pytest.raises(RuntimeError, match="파싱 에러"):
            service.execute("task-1")

        last_save = task_repo.save.call_args_list[-1][0][0]
        assert last_save.status == TaskStatus.FAILED
        assert "파싱 에러" in last_save.error

    def test_resume_selection_완료시_odd_label만_실행(self, service, task_repo, selection_repo, odd_tag_repo, label_repo, phase_provider):
        task = _make_task(
            last_completed_phase=Stage.SELECTION,
            sel_total=100,
            odd_total=80,
            label_total=60,
        )
        task_repo.find_by_id.return_value = task

        odd_result = StageResult(total=80, loaded=70, rejected=10)
        label_result = StageResult(total=60, loaded=55, rejected=5)

        odd_runner = MagicMock()
        label_runner = MagicMock()

        odd_runner.run.side_effect = lambda t, tid, vids=None: (odd_result, t.with_completed_phase(Stage.ODD_TAGGING))
        label_runner.run.side_effect = lambda t, tid, vids=None: (label_result, t.with_completed_phase(Stage.AUTO_LABELING))

        phase_provider.get.side_effect = lambda s: {
            Stage.ODD_TAGGING: odd_runner,
            Stage.AUTO_LABELING: label_runner,
        }[s]

        selection_repo.find_all_ids_by_task.return_value = {1, 2, 3}
        odd_tag_repo.find_all_video_ids_by_task.return_value = {1, 2}
        label_repo.find_all_video_ids_by_task.return_value = {1, 2}

        service.execute("task-1")

        # selection runner는 호출되지 않아야 함
        assert Stage.SELECTION not in [c[0][0] for c in phase_provider.get.call_args_list]
        # odd, label runner만 호출
        called_stages = [c[0][0] for c in phase_provider.get.call_args_list]
        assert Stage.ODD_TAGGING in called_stages
        assert Stage.AUTO_LABELING in called_stages

    def test_resume_odd_tagging_완료시_auto_labeling만_실행(
        self, service, task_repo, selection_repo, odd_tag_repo, label_repo, phase_provider
    ):
        """last_completed_phase=ODD_TAGGING이면 AUTO_LABELING만 실행하고,
        SELECTION/ODD_TAGGING은 기존 progress에서 StageResult를 생성한다."""
        task = _make_task(
            last_completed_phase=Stage.ODD_TAGGING,
            sel_total=100,
            odd_total=80,
            label_total=60,
        )
        # 스킵 대상 Phase에 이미 progress가 있는 상태를 시뮬레이션
        task = task.with_progress(
            Stage.SELECTION, StageProgress(total=100, processed=90, rejected=10)
        )
        task = task.with_progress(
            Stage.ODD_TAGGING, StageProgress(total=80, processed=70, rejected=10)
        )
        task_repo.find_by_id.return_value = task

        label_result = StageResult(total=60, loaded=55, rejected=5)
        label_runner = MagicMock()
        label_runner.run.side_effect = lambda t, tid, vids=None: (
            label_result,
            t.with_completed_phase(Stage.AUTO_LABELING),
        )

        phase_provider.get.side_effect = lambda s: {
            Stage.AUTO_LABELING: label_runner,
        }[s]

        selection_repo.find_all_ids_by_task.return_value = {1, 2, 3}
        odd_tag_repo.find_all_video_ids_by_task.return_value = {1, 2, 3}
        label_repo.find_all_video_ids_by_task.return_value = {1, 2}

        service.execute("task-1")

        # SELECTION, ODD_TAGGING runner는 호출되지 않아야 함
        called_stages = [c[0][0] for c in phase_provider.get.call_args_list]
        assert Stage.SELECTION not in called_stages
        assert Stage.ODD_TAGGING not in called_stages
        assert Stage.AUTO_LABELING in called_stages

        # label_runner만 실행됨
        label_runner.run.assert_called_once()

        # 완료된 task의 result에 스킵된 Phase의 StageResult가 기존 progress 기반으로 생성됨
        last_save = task_repo.save.call_args_list[-1][0][0]
        assert last_save.status == TaskStatus.COMPLETED
        result = last_save.result
        # 스킵된 Phase: 기존 progress에서 StageResult 생성
        assert result.selection == StageResult(total=100, loaded=90, rejected=10)
        assert result.odd_tagging == StageResult(total=80, loaded=70, rejected=10)
        # 실행된 Phase: runner 반환값 사용
        assert result.auto_labeling == label_result

    def test_build_result_교집합_없음(
        self, service, task_repo, selection_repo, odd_tag_repo, label_repo, phase_provider
    ):
        """selection_ids와 odd/label_ids의 교집합이 0이면 fully_linked=0, partial=전체"""
        task = _make_task()
        task_repo.find_by_id.return_value = task

        sel_result = StageResult(total=100, loaded=3, rejected=0)
        odd_result = StageResult(total=80, loaded=2, rejected=0)
        label_result = StageResult(total=60, loaded=2, rejected=0)

        sel_runner = MagicMock()
        odd_runner = MagicMock()
        label_runner = MagicMock()

        sel_runner.run.side_effect = lambda t, tid, vids=None: (sel_result, t.with_completed_phase(Stage.SELECTION))
        odd_runner.run.side_effect = lambda t, tid, vids=None: (odd_result, t.with_completed_phase(Stage.ODD_TAGGING))
        label_runner.run.side_effect = lambda t, tid, vids=None: (label_result, t.with_completed_phase(Stage.AUTO_LABELING))

        phase_provider.get.side_effect = lambda s: {
            Stage.SELECTION: sel_runner,
            Stage.ODD_TAGGING: odd_runner,
            Stage.AUTO_LABELING: label_runner,
        }[s]

        # 교집합이 전혀 없는 ID 세트
        selection_repo.find_all_ids_by_task.return_value = {1, 2, 3}
        odd_tag_repo.find_all_video_ids_by_task.return_value = {4, 5}
        label_repo.find_all_video_ids_by_task.return_value = {6, 7}

        service.execute("task-1")

        last_save = task_repo.save.call_args_list[-1][0][0]
        result = last_save.result
        assert result.fully_linked == 0
        assert result.partial == 3

    def test_build_result_전체_일치(
        self, service, task_repo, selection_repo, odd_tag_repo, label_repo, phase_provider
    ):
        """모든 ID가 동일하면 fully_linked=전체, partial=0"""
        task = _make_task()
        task_repo.find_by_id.return_value = task

        sel_result = StageResult(total=100, loaded=3, rejected=0)
        odd_result = StageResult(total=80, loaded=3, rejected=0)
        label_result = StageResult(total=60, loaded=3, rejected=0)

        sel_runner = MagicMock()
        odd_runner = MagicMock()
        label_runner = MagicMock()

        sel_runner.run.side_effect = lambda t, tid, vids=None: (sel_result, t.with_completed_phase(Stage.SELECTION))
        odd_runner.run.side_effect = lambda t, tid, vids=None: (odd_result, t.with_completed_phase(Stage.ODD_TAGGING))
        label_runner.run.side_effect = lambda t, tid, vids=None: (label_result, t.with_completed_phase(Stage.AUTO_LABELING))

        phase_provider.get.side_effect = lambda s: {
            Stage.SELECTION: sel_runner,
            Stage.ODD_TAGGING: odd_runner,
            Stage.AUTO_LABELING: label_runner,
        }[s]

        # 전체 일치하는 ID 세트
        selection_repo.find_all_ids_by_task.return_value = {1, 2, 3}
        odd_tag_repo.find_all_video_ids_by_task.return_value = {1, 2, 3}
        label_repo.find_all_video_ids_by_task.return_value = {1, 2, 3}

        service.execute("task-1")

        last_save = task_repo.save.call_args_list[-1][0][0]
        result = last_save.result
        assert result.fully_linked == 3
        assert result.partial == 0
