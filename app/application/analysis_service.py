import csv
import json
import logging
from datetime import datetime
from pathlib import Path

from app.application.parsers import detect_parser
from app.application.validators import LabelValidator, OddValidator
from app.domain.enums import RejectionReason, Stage
from app.domain.models import AnalysisResult, Rejection, StageResult
from app.domain.ports import (
    LabelRepository,
    OddTagRepository,
    RejectionRepository,
    SelectionRepository,
)

logger = logging.getLogger(__name__)

CHUNK_SIZE = 5000


class AnalysisService:
    """데이터 정제 → 적재 파이프라인 서비스 (Command)"""

    def __init__(
        self,
        selection_repo: SelectionRepository,
        odd_tag_repo: OddTagRepository,
        label_repo: LabelRepository,
        rejection_repo: RejectionRepository,
        data_dir: Path,
    ) -> None:
        self._selection_repo = selection_repo
        self._odd_tag_repo = odd_tag_repo
        self._label_repo = label_repo
        self._rejection_repo = rejection_repo
        self._data_dir = data_dir

    def analyze(self) -> AnalysisResult:
        """3개 파일을 읽어 정제 → 적재 → 분석 결과를 반환한다."""
        self._clear_all()

        selection_result = self._process_selections()

        valid_selection_ids = self._selection_repo.find_all_ids()
        odd_result = self._process_odds(valid_selection_ids)
        label_result = self._process_labels(valid_selection_ids)

        odd_video_ids = self._odd_tag_repo.find_all_video_ids()
        label_video_ids = self._label_repo.find_all_video_ids()
        fully_linked = len(valid_selection_ids & odd_video_ids & label_video_ids)
        partial = len(valid_selection_ids) - fully_linked

        logger.info(
            "분석 완료: selection=%d, odd=%d, label=%d, fully_linked=%d",
            selection_result.loaded,
            odd_result.loaded,
            label_result.loaded,
            fully_linked,
        )

        return AnalysisResult(
            selection=selection_result,
            odd_tagging=odd_result,
            auto_labeling=label_result,
            fully_linked=fully_linked,
            partial=partial,
        )

    def _process_selections(self) -> StageResult:
        """selections.json 청크 단위 파싱 + 적재"""
        path = self._data_dir / "selections.json"
        with open(path) as f:
            raw_list = json.load(f)

        total = len(raw_list)
        loaded = 0
        rejected = 0
        now = datetime.now()

        for chunk_start in range(0, total, CHUNK_SIZE):
            chunk = raw_list[chunk_start : chunk_start + CHUNK_SIZE]
            selections = []
            rejections = []

            for raw in chunk:
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

            loaded += len(selections)
            rejected += len(rejections)

        logger.info("Selection: total=%d, loaded=%d, rejected=%d", total, loaded, rejected)
        return StageResult(total=total, loaded=loaded, rejected=rejected)

    def _process_odds(self, valid_selection_ids: set[int]) -> StageResult:
        """odds.csv 전체 검증 (중복 검사) + 청크 적재"""
        path = self._data_dir / "odds.csv"

        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))

        total = len(rows)
        validator = OddValidator()
        valid, rejections = validator.validate_batch(rows, valid_selection_ids)

        if valid:
            self._odd_tag_repo.save_all(valid)
        if rejections:
            self._rejection_repo.save_all(rejections)

        loaded = len(valid)
        rejected = len(rejections)

        logger.info("ODD: total=%d, loaded=%d, rejected=%d", total, loaded, rejected)
        return StageResult(total=total, loaded=loaded, rejected=rejected)

    def _process_labels(self, valid_selection_ids: set[int]) -> StageResult:
        """labels.csv 전체 검증 (중복 검사) + 청크 적재"""
        path = self._data_dir / "labels.csv"

        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))

        total = len(rows)
        validator = LabelValidator()
        valid, rejections = validator.validate_batch(rows, valid_selection_ids)

        if valid:
            self._label_repo.save_all(valid)
        if rejections:
            self._rejection_repo.save_all(rejections)

        loaded = len(valid)
        rejected = len(rejections)

        logger.info("Label: total=%d, loaded=%d, rejected=%d", total, loaded, rejected)
        return StageResult(total=total, loaded=loaded, rejected=rejected)

    def _clear_all(self) -> None:
        """재분석을 위해 모든 데이터를 초기화한다."""
        self._rejection_repo.delete_all()
        self._label_repo.delete_all()
        self._odd_tag_repo.delete_all()
        self._selection_repo.delete_all()
