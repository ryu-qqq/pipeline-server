import itertools
import logging
from abc import ABC, abstractmethod
from datetime import datetime

from app.application.label_refiner import LabelRefiner
from app.application.odd_tag_refiner import OddTagRefiner
from app.application.selection_refiner import SelectionRefiner
from app.domain.enums import RejectionReason, Stage
from app.domain.models import AnalyzeTask, Rejection
from app.domain.ports import (
    LabelRepository,
    OddTagRepository,
    RawDataRepository,
    RejectionRepository,
    SelectionRepository,
    TaskRepository,
)
from app.domain.value_objects import StageProgress, StageResult

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 5000


class PhaseRunnerProvider:
    """Stage에 맞는 PhaseRunner를 반환하는 프로바이더"""

    def __init__(self) -> None:
        self._runners: dict[Stage, "PhaseRunner"] = {}

    def register(self, stage: Stage, runner: "PhaseRunner") -> None:
        self._runners[stage] = runner

    def get(self, stage: Stage) -> "PhaseRunner":
        runner = self._runners.get(stage)
        if runner is None:
            raise ValueError(f"등록되지 않은 Phase: {stage}")
        return runner


class PhaseRunner(ABC):
    """Phase 실행 전략 — 스트리밍 조회 → 청크 단위 정제 + 적재 → 진행률 추적

    중복 탐지는 MySQL UNIQUE 제약 + INSERT IGNORE에 위임한다.
    """

    def __init__(
        self,
        raw_data_repo: RawDataRepository,
        task_repo: TaskRepository,
        rejection_repo: RejectionRepository,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self._raw_data_repo = raw_data_repo
        self._task_repo = task_repo
        self._rejection_repo = rejection_repo
        self._chunk_size = chunk_size

    def run(
        self, task: AnalyzeTask, task_id: str, valid_selection_ids: set[int] | None = None
    ) -> tuple[StageResult, AnalyzeTask]:
        """Phase를 스트리밍으로 실행하고 갱신된 task를 반환한다.

        청크 단위로 정제 + 적재하되, 진행률은 Phase 완료 시 1번만 갱신한다.
        total은 Task 생성 시 확정된 값을 사용한다.
        """
        rows = self._raw_data_repo.find_by_task_and_source(task_id, self.source)

        loaded_count = 0
        rejected_count = 0

        while True:
            chunk = list(itertools.islice(rows, self._chunk_size))
            if not chunk:
                break

            valid, rejections = self._refine_chunk(task_id, chunk, valid_selection_ids or set())

            if valid:
                inserted = self._save_valid_ignore_duplicates(valid)
                duplicate_count = len(valid) - inserted
                loaded_count += inserted

                if duplicate_count > 0:
                    rejections.extend(self._build_duplicate_rejections(task_id, duplicate_count))

            if rejections:
                self._rejection_repo.save_all(rejections)
                rejected_count += len(rejections)

        # Phase 완료 — 진행률 1번 갱신 + resume 포인트 기록
        progress = task.get_progress_for(self.stage)
        task = task.with_progress(
            self.stage, StageProgress(total=progress.total, processed=loaded_count, rejected=rejected_count)
        )
        task = task.with_completed_phase(self.stage)
        self._task_repo.save(task)

        logger.info("%s: total=%d, loaded=%d, rejected=%d", self.stage.value, progress.total, loaded_count, rejected_count)
        return StageResult(total=progress.total, loaded=loaded_count, rejected=rejected_count), task

    @property
    @abstractmethod
    def stage(self) -> Stage: ...

    @property
    @abstractmethod
    def source(self) -> str: ...

    @abstractmethod
    def _refine_single(self, task_id: str, row: dict, valid_selection_ids: set[int]) -> object:
        """단건 정제 — 성공 시 도메인 모델, 실패 시 Rejection 또는 list[Rejection] 반환."""
        ...

    @abstractmethod
    def _save_valid_ignore_duplicates(self, items: list) -> int:
        """유효 데이터를 INSERT IGNORE로 저장하고, 실제 적재된 건수를 반환한다."""
        ...

    def _refine_chunk(
        self, task_id: str, chunk: list[dict], valid_selection_ids: set[int]
    ) -> tuple[list, list[Rejection]]:
        """청크를 정제하여 valid/rejected로 분리한다."""
        valid = []
        rejections = []
        for row in chunk:
            result = self._refine_single(task_id, row, valid_selection_ids)
            if isinstance(result, list):
                rejections.extend(result)
            elif isinstance(result, Rejection):
                rejections.append(result)
            else:
                valid.append(result)
        return valid, rejections

    def _build_duplicate_rejections(self, task_id: str, count: int) -> list[Rejection]:
        """INSERT IGNORE에서 무시된 중복 건수만큼 Rejection을 생성한다."""
        now = datetime.now()
        reason = RejectionReason.DUPLICATE_TAGGING if self.stage == Stage.ODD_TAGGING else RejectionReason.DUPLICATE_LABEL
        return [
            Rejection(
                task_id=task_id,
                stage=self.stage,
                reason=reason,
                source_id="batch",
                field="unique_constraint",
                detail=f"UNIQUE 제약 위반으로 {count}건 무시됨",
                created_at=now,
            )
        ]


class SelectionPhaseRunner(PhaseRunner):
    """Selection Phase — SelectionRefiner 정제 + 적재"""

    def __init__(
        self,
        raw_data_repo: RawDataRepository,
        task_repo: TaskRepository,
        rejection_repo: RejectionRepository,
        selection_repo: SelectionRepository,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        super().__init__(raw_data_repo, task_repo, rejection_repo, chunk_size)
        self._selection_repo = selection_repo
        self._refiner = SelectionRefiner()

    @property
    def stage(self) -> Stage:
        return Stage.SELECTION

    @property
    def source(self) -> str:
        return "selections"

    def _refine_single(self, task_id: str, row: dict, valid_selection_ids: set[int]) -> object:
        return self._refiner.refine_single(task_id, row)

    def _save_valid_ignore_duplicates(self, items: list) -> int:
        return self._selection_repo.save_all(items)


class OddTagPhaseRunner(PhaseRunner):
    """ODD Tagging Phase — OddTagRefiner 정제 + 적재"""

    def __init__(
        self,
        raw_data_repo: RawDataRepository,
        task_repo: TaskRepository,
        rejection_repo: RejectionRepository,
        odd_tag_repo: OddTagRepository,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        super().__init__(raw_data_repo, task_repo, rejection_repo, chunk_size)
        self._odd_tag_repo = odd_tag_repo
        self._refiner = OddTagRefiner()

    @property
    def stage(self) -> Stage:
        return Stage.ODD_TAGGING

    @property
    def source(self) -> str:
        return "odds"

    def _refine_single(self, task_id: str, row: dict, valid_selection_ids: set[int]) -> object:
        return self._refiner.refine_single(task_id, row)

    def _save_valid_ignore_duplicates(self, items: list) -> int:
        return self._odd_tag_repo.save_all(items)


class LabelPhaseRunner(PhaseRunner):
    """Auto Labeling Phase — LabelRefiner 정제 + 적재"""

    def __init__(
        self,
        raw_data_repo: RawDataRepository,
        task_repo: TaskRepository,
        rejection_repo: RejectionRepository,
        label_repo: LabelRepository,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        super().__init__(raw_data_repo, task_repo, rejection_repo, chunk_size)
        self._label_repo = label_repo
        self._refiner = LabelRefiner()

    @property
    def stage(self) -> Stage:
        return Stage.AUTO_LABELING

    @property
    def source(self) -> str:
        return "labels"

    def _refine_single(self, task_id: str, row: dict, valid_selection_ids: set[int]) -> object:
        return self._refiner.refine_single(task_id, row)

    def _save_valid_ignore_duplicates(self, items: list) -> int:
        return self._label_repo.save_all(items)
