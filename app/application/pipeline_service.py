import json
import logging
from datetime import datetime

from app.application.parsers import detect_parser
from app.application.validators import LabelValidator, OddValidator
from app.domain.enums import RejectionReason, Stage, TaskStatus
from app.domain.models import Rejection, StageResult
from app.domain.ports import (
    LabelRepository,
    OddTagRepository,
    RawDataRepository,
    RejectionRepository,
    SelectionRepository,
    StageProgress,
    TaskRepository,
)

logger = logging.getLogger(__name__)

CHUNK_SIZE = 5000


class PipelineService:
    """정제 파이프라인 서비스 — MongoDB에서 읽기 → 정제 → MySQL 적재"""

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
        """task_id에 해당하는 원본 데이터를 정제하여 MySQL에 적재한다."""
        self._task_repo.update_status(task_id, TaskStatus.PROCESSING)

        try:
            # 기존 MySQL 데이터 초기화 (재분석 지원)
            self._clear_mysql()

            # Phase 1: Selection 정제
            sel_result = self._process_selections(task_id)
            self._task_repo.update_progress(
                task_id,
                Stage.SELECTION,
                StageProgress(total=sel_result.total, processed=sel_result.loaded, rejected=sel_result.rejected),
            )

            # Phase 2: ODD 정제
            valid_selection_ids = self._selection_repo.find_all_ids()
            odd_result = self._process_odds(task_id, valid_selection_ids)
            self._task_repo.update_progress(
                task_id,
                Stage.ODD_TAGGING,
                StageProgress(total=odd_result.total, processed=odd_result.loaded, rejected=odd_result.rejected),
            )

            # Phase 3: Label 정제
            label_result = self._process_labels(task_id, valid_selection_ids)
            self._task_repo.update_progress(
                task_id,
                Stage.AUTO_LABELING,
                StageProgress(total=label_result.total, processed=label_result.loaded, rejected=label_result.rejected),
            )

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

    def _process_selections(self, task_id: str) -> StageResult:
        raw_list = self._raw_data_repo.find_by_task_and_source(task_id, "selections")

        total = len(raw_list)
        selections = []
        rejections = []
        now = datetime.now()

        for raw in raw_list:
            try:
                parser = detect_parser(raw)
                selection = parser.parse(raw)
                selections.append(selection)
            except (ValueError, TypeError, KeyError) as e:
                rejections.append(
                    Rejection(
                        record_identifier=f"selection_id={raw.get('id', '?')}",
                        stage=Stage.SELECTION,
                        reason=RejectionReason.INVALID_FORMAT,
                        detail=str(e),
                        raw_data=json.dumps(raw, ensure_ascii=False, default=str),
                        created_at=now,
                    )
                )

        if selections:
            self._selection_repo.save_all(selections)
        if rejections:
            self._rejection_repo.save_all(rejections)

        logger.info("Selection: total=%d, loaded=%d, rejected=%d", total, len(selections), len(rejections))
        return StageResult(total=total, loaded=len(selections), rejected=len(rejections))

    def _process_odds(self, task_id: str, valid_selection_ids: set[int]) -> StageResult:
        rows = self._raw_data_repo.find_by_task_and_source(task_id, "odds")

        total = len(rows)
        validator = OddValidator()
        valid, rejections = validator.validate_batch(rows, valid_selection_ids)

        if valid:
            self._odd_tag_repo.save_all(valid)
        if rejections:
            self._rejection_repo.save_all(rejections)

        logger.info("ODD: total=%d, loaded=%d, rejected=%d", total, len(valid), len(rejections))
        return StageResult(total=total, loaded=len(valid), rejected=len(rejections))

    def _process_labels(self, task_id: str, valid_selection_ids: set[int]) -> StageResult:
        rows = self._raw_data_repo.find_by_task_and_source(task_id, "labels")

        total = len(rows)
        validator = LabelValidator()
        valid, rejections = validator.validate_batch(rows, valid_selection_ids)

        if valid:
            self._label_repo.save_all(valid)
        if rejections:
            self._rejection_repo.save_all(rejections)

        logger.info("Label: total=%d, loaded=%d, rejected=%d", total, len(valid), len(rejections))
        return StageResult(total=total, loaded=len(valid), rejected=len(rejections))

    def _clear_mysql(self) -> None:
        self._rejection_repo.delete_all()
        self._label_repo.delete_all()
        self._odd_tag_repo.delete_all()
        self._selection_repo.delete_all()
