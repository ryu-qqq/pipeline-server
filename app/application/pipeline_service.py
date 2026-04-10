import logging

from app.application.phase_runners import PhaseRunnerProvider
from app.domain.enums import Stage
from app.domain.models import AnalysisResult, AnalyzeTask
from app.domain.ports import (
    CacheRepository,
    LabelRepository,
    OddTagRepository,
    SelectionRepository,
    TaskRepository,
)
from app.domain.value_objects import StageResult

logger = logging.getLogger(__name__)


class PipelineService:
    """정제 파이프라인 오케스트레이터 — Phase 순서 제어 + 완료/실패 관리"""

    def __init__(
        self,
        task_repo: TaskRepository,
        selection_repo: SelectionRepository,
        odd_tag_repo: OddTagRepository,
        label_repo: LabelRepository,
        cache_repo: CacheRepository,
        phase_runner_provider: PhaseRunnerProvider,
    ) -> None:
        self._task_repo = task_repo
        self._selection_repo = selection_repo
        self._odd_tag_repo = odd_tag_repo
        self._label_repo = label_repo
        self._cache_repo = cache_repo
        self._phase_runner_provider = phase_runner_provider

    def execute(self, task_id: str) -> None:
        """정제 파이프라인을 실행한다.

        실패 후 재시도 시 last_completed_phase 이후 Phase부터 재개한다.
        """
        task = self._task_repo.find_by_id(task_id)

        task = task.start_processing()
        self._task_repo.save(task)

        try:
            results, task = self._run_phases(task, task_id)
            result_dict = self._build_result(task_id, results)

            task = task.complete_with(result_dict)
            self._task_repo.save(task)
            self._cache_repo.invalidate_all()

            logger.info("파이프라인 완료: task_id=%s", task_id)

        except Exception as e:
            logger.exception("파이프라인 실패: task_id=%s", task_id)
            task = task.fail_with(str(e))
            self._task_repo.save(task)
            raise

    # === Phase 오케스트레이션 ===

    def _run_phases(
        self, task: AnalyzeTask, task_id: str
    ) -> tuple[dict[Stage, StageResult], AnalyzeTask]:
        results: dict[Stage, StageResult] = {}
        valid_selection_ids: set[int] | None = None

        for stage in AnalyzeTask._STAGE_ORDER:
            if task.should_run_phase(stage):
                runner = self._phase_runner_provider.get(stage)
                result, task = runner.run(task, task_id, valid_selection_ids)
            else:
                progress = task.get_progress_for(stage)
                result = StageResult(total=progress.total, loaded=progress.processed, rejected=progress.rejected)

            results[stage] = result

            if stage == Stage.SELECTION:
                valid_selection_ids = self._selection_repo.find_all_ids_by_task(task_id)

        return results, task

    def _build_result(self, task_id: str, results: dict[Stage, StageResult]) -> AnalysisResult:
        """Phase 결과 + 통합 통계(fully_linked)를 조합한다.

        fully_linked: Selection + OddTag + Label 3단계가 모두 존재하는 영상 수
        partial: Selection은 있지만 OddTag 또는 Label이 없는 영상 수
        """
        valid_selection_ids = self._selection_repo.find_all_ids_by_task(task_id)
        odd_video_ids = self._odd_tag_repo.find_all_video_ids_by_task(task_id)
        label_video_ids = self._label_repo.find_all_video_ids_by_task(task_id)
        fully_linked = len(valid_selection_ids & odd_video_ids & label_video_ids)
        partial = len(valid_selection_ids) - fully_linked

        return AnalysisResult(
            selection=results[Stage.SELECTION],
            odd_tagging=results[Stage.ODD_TAGGING],
            auto_labeling=results[Stage.AUTO_LABELING],
            fully_linked=fully_linked,
            partial=partial,
        )
