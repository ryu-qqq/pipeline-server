import json
import logging
from datetime import datetime

from app.application.parsers import detect_parser
from app.application.validators import LabelValidator, OddValidator
from app.domain.enums import RejectionReason, Stage, TaskStatus
from app.domain.models import AnalyzeTask, Rejection, StageProgress, StageResult
from app.domain.ports import (
    LabelRepository,
    OddTagRepository,
    RawDataRepository,
    RejectionRepository,
    SelectionRepository,
    TaskRepository,
)

logger = logging.getLogger(__name__)

CHUNK_SIZE = 5000

# Stage 순서 — resume 로직에서 완료된 Phase 이후부터 실행하기 위한 참조
_STAGE_ORDER: list[Stage] = [Stage.SELECTION, Stage.ODD_TAGGING, Stage.AUTO_LABELING]


class PipelineService:
    """정제 파이프라인 서비스 — MongoDB에서 읽기 -> 정제 -> MySQL 적재"""

    def __init__(
        self,
        raw_data_repo: RawDataRepository,
        task_repo: TaskRepository,
        selection_repo: SelectionRepository,
        odd_tag_repo: OddTagRepository,
        label_repo: LabelRepository,
        rejection_repo: RejectionRepository,
    ) -> None:
        self._raw_data_repo = raw_data_repo
        self._task_repo = task_repo
        self._selection_repo = selection_repo
        self._odd_tag_repo = odd_tag_repo
        self._label_repo = label_repo
        self._rejection_repo = rejection_repo

    def execute(self, task_id: str) -> None:
        """task_id에 해당하는 원본 데이터를 정제하여 MySQL에 적재한다.

        실패 후 재시도 시 last_completed_phase 이후 Phase부터 실행한다.
        """
        task = self._task_repo.find_by_id(task_id)
        resume_after = task.last_completed_phase if task else None

        self._task_repo.update_status(task_id, TaskStatus.PROCESSING)

        try:
            # resume이 아닌 경우 기존 MySQL 데이터 초기화
            if resume_after is None:
                self._clear_mysql()
            else:
                # resume 대상 Phase의 기존 데이터만 삭제 (부분 적재 중복 방지)
                if self._should_run(Stage.SELECTION, resume_after):
                    self._selection_repo.delete_all()
                if self._should_run(Stage.ODD_TAGGING, resume_after):
                    self._odd_tag_repo.delete_all()
                if self._should_run(Stage.AUTO_LABELING, resume_after):
                    self._label_repo.delete_all()
                # rejection은 stage별 삭제 미지원 — 재실행 대상이 있으면 전체 삭제
                self._rejection_repo.delete_all()

            # Phase 1: Selection 정제
            if self._should_run(Stage.SELECTION, resume_after):
                sel_result = self._process_selections(task_id)
                self._task_repo.update_last_completed_phase(task_id, Stage.SELECTION)
            else:
                sel_result = self._build_skip_result(task, Stage.SELECTION)

            # Phase 2: ODD 정제
            valid_selection_ids = self._selection_repo.find_all_ids()
            if self._should_run(Stage.ODD_TAGGING, resume_after):
                odd_result = self._process_odds(task_id, valid_selection_ids)
                self._task_repo.update_last_completed_phase(task_id, Stage.ODD_TAGGING)
            else:
                odd_result = self._build_skip_result(task, Stage.ODD_TAGGING)

            # Phase 3: Label 정제
            if self._should_run(Stage.AUTO_LABELING, resume_after):
                label_result = self._process_labels(task_id, valid_selection_ids)
                self._task_repo.update_last_completed_phase(task_id, Stage.AUTO_LABELING)
            else:
                label_result = self._build_skip_result(task, Stage.AUTO_LABELING)

            # 통합 통계
            odd_video_ids = self._odd_tag_repo.find_all_video_ids()
            label_video_ids = self._label_repo.find_all_video_ids()
            fully_linked = len(valid_selection_ids & odd_video_ids & label_video_ids)
            partial = len(valid_selection_ids) - fully_linked

            result = {
                "selection": {"total": sel_result.total, "loaded": sel_result.loaded, "rejected": sel_result.rejected},
                "odd_tagging": {
                    "total": odd_result.total,
                    "loaded": odd_result.loaded,
                    "rejected": odd_result.rejected,
                },
                "auto_labeling": {
                    "total": label_result.total,
                    "loaded": label_result.loaded,
                    "rejected": label_result.rejected,
                },
                "fully_linked": fully_linked,
                "partial": partial,
            }

            self._task_repo.complete(task_id, result)
            logger.info("파이프라인 완료: task_id=%s, fully_linked=%d", task_id, fully_linked)

        except Exception as e:
            logger.exception("파이프라인 실패: task_id=%s", task_id)
            self._task_repo.fail(task_id, str(e))
            raise

    # === Phase 실행 판단 ===

    @staticmethod
    def _should_run(phase: Stage, resume_after: Stage | None) -> bool:
        """해당 Phase를 실행해야 하는지 판단한다.

        resume_after가 None이면 모든 Phase 실행.
        resume_after가 설정되면 해당 Phase 이후의 Phase만 실행.
        """
        if resume_after is None:
            return True
        resume_idx = _STAGE_ORDER.index(resume_after)
        phase_idx = _STAGE_ORDER.index(phase)
        return phase_idx > resume_idx

    @staticmethod
    def _build_skip_result(task: AnalyzeTask | None, stage: Stage) -> StageResult:
        """이미 완료된 Phase의 결과를 기존 Task에서 읽어온다."""
        if task is None:
            return StageResult(total=0, loaded=0, rejected=0)

        progress = {
            Stage.SELECTION: task.selection_progress,
            Stage.ODD_TAGGING: task.odd_tagging_progress,
            Stage.AUTO_LABELING: task.auto_labeling_progress,
        }.get(stage)

        if progress is None:
            return StageResult(total=0, loaded=0, rejected=0)
        return StageResult(total=progress.total, loaded=progress.processed, rejected=progress.rejected)

    # === Phase 처리 (청크 단위 진행률 업데이트) ===

    def _process_selections(self, task_id: str) -> StageResult:
        raw_list = self._raw_data_repo.find_by_task_and_source(task_id, "selections")

        total = len(raw_list)
        all_selections = []
        all_rejections = []
        now = datetime.now()

        for raw in raw_list:
            try:
                parser = detect_parser(raw)
                selection = parser.parse(raw)
                all_selections.append(selection)
            except (ValueError, TypeError, KeyError) as e:
                all_rejections.append(
                    Rejection(
                        record_identifier=f"selection_id={raw.get('id', '?')}",
                        stage=Stage.SELECTION,
                        reason=RejectionReason.INVALID_FORMAT,
                        detail=str(e),
                        raw_data=json.dumps(raw, ensure_ascii=False, default=str),
                        created_at=now,
                    )
                )

        # 청크 단위로 적재하면서 진행률 업데이트
        loaded_count = 0
        rejected_count = len(all_rejections)

        # rejection은 한번에 적재 (파싱 단계에서 이미 분류 완료)
        if all_rejections:
            self._rejection_repo.save_all(all_rejections)

        for i in range(0, len(all_selections), CHUNK_SIZE):
            chunk = all_selections[i : i + CHUNK_SIZE]
            self._selection_repo.save_all(chunk)
            loaded_count += len(chunk)

            self._task_repo.update_progress(
                task_id,
                Stage.SELECTION,
                StageProgress(total=total, processed=loaded_count, rejected=rejected_count),
            )

        # 전부 rejection인 경우에도 최종 진행률 반영
        if not all_selections:
            self._task_repo.update_progress(
                task_id,
                Stage.SELECTION,
                StageProgress(total=total, processed=0, rejected=rejected_count),
            )

        logger.info("Selection: total=%d, loaded=%d, rejected=%d", total, loaded_count, rejected_count)
        return StageResult(total=total, loaded=loaded_count, rejected=rejected_count)

    def _process_odds(self, task_id: str, valid_selection_ids: set[int]) -> StageResult:
        rows = self._raw_data_repo.find_by_task_and_source(task_id, "odds")

        total = len(rows)
        validator = OddValidator()
        # 중복 검사는 전체 기준으로 수행
        valid, rejections = validator.validate_batch(rows, valid_selection_ids)

        # rejection 한번에 적재
        if rejections:
            self._rejection_repo.save_all(rejections)
        rejected_count = len(rejections)

        # 유효 데이터를 청크 단위로 적재하면서 진행률 업데이트
        loaded_count = 0
        for i in range(0, len(valid), CHUNK_SIZE):
            chunk = valid[i : i + CHUNK_SIZE]
            self._odd_tag_repo.save_all(chunk)
            loaded_count += len(chunk)

            self._task_repo.update_progress(
                task_id,
                Stage.ODD_TAGGING,
                StageProgress(total=total, processed=loaded_count, rejected=rejected_count),
            )

        # 전부 rejection인 경우에도 최종 진행률 반영
        if not valid:
            self._task_repo.update_progress(
                task_id,
                Stage.ODD_TAGGING,
                StageProgress(total=total, processed=0, rejected=rejected_count),
            )

        logger.info("ODD: total=%d, loaded=%d, rejected=%d", total, loaded_count, rejected_count)
        return StageResult(total=total, loaded=loaded_count, rejected=rejected_count)

    def _process_labels(self, task_id: str, valid_selection_ids: set[int]) -> StageResult:
        rows = self._raw_data_repo.find_by_task_and_source(task_id, "labels")

        total = len(rows)
        validator = LabelValidator()
        # 중복 검사는 전체 기준으로 수행
        valid, rejections = validator.validate_batch(rows, valid_selection_ids)

        # rejection 한번에 적재
        if rejections:
            self._rejection_repo.save_all(rejections)
        rejected_count = len(rejections)

        # 유효 데이터를 청크 단위로 적재하면서 진행률 업데이트
        loaded_count = 0
        for i in range(0, len(valid), CHUNK_SIZE):
            chunk = valid[i : i + CHUNK_SIZE]
            self._label_repo.save_all(chunk)
            loaded_count += len(chunk)

            self._task_repo.update_progress(
                task_id,
                Stage.AUTO_LABELING,
                StageProgress(total=total, processed=loaded_count, rejected=rejected_count),
            )

        # 전부 rejection인 경우에도 최종 진행률 반영
        if not valid:
            self._task_repo.update_progress(
                task_id,
                Stage.AUTO_LABELING,
                StageProgress(total=total, processed=0, rejected=rejected_count),
            )

        logger.info("Label: total=%d, loaded=%d, rejected=%d", total, loaded_count, rejected_count)
        return StageResult(total=total, loaded=loaded_count, rejected=rejected_count)

    def _clear_mysql(self) -> None:
        self._rejection_repo.delete_all()
        self._label_repo.delete_all()
        self._odd_tag_repo.delete_all()
        self._selection_repo.delete_all()
