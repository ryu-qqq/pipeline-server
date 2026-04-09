import csv
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from app.domain.enums import TaskStatus
from app.domain.ports import AnalyzeTask, RawDataRepository, StageProgress, TaskDispatcher, TaskRepository

logger = logging.getLogger(__name__)


class AnalysisService:
    """분석 요청 접수 서비스 (Command) — 파일 → MongoDB 적재 + 비동기 작업 발행"""

    def __init__(
        self,
        raw_data_repo: RawDataRepository,
        task_repo: TaskRepository,
        task_dispatcher: TaskDispatcher,
        data_dir: Path,
    ) -> None:
        self._raw_data_repo = raw_data_repo
        self._task_repo = task_repo
        self._task_dispatcher = task_dispatcher
        self._data_dir = data_dir

    def submit(self) -> str:
        """3개 파일을 MongoDB에 적재하고 비동기 정제 작업을 발행한다."""
        task_id = str(uuid.uuid4())
        now = datetime.now()

        sel_count = self._load_selections(task_id)
        odd_count = self._load_odds(task_id)
        label_count = self._load_labels(task_id)

        task = AnalyzeTask(
            task_id=task_id,
            status=TaskStatus.PENDING,
            selection_progress=StageProgress(total=sel_count),
            odd_tagging_progress=StageProgress(total=odd_count),
            auto_labeling_progress=StageProgress(total=label_count),
            created_at=now,
        )
        self._task_repo.create(task)

        # 비동기 작업 발행 — Port를 통해 (Celery를 직접 모름)
        self._task_dispatcher.dispatch(task_id)

        logger.info(
            "분석 접수: task_id=%s, selections=%d, odds=%d, labels=%d",
            task_id,
            sel_count,
            odd_count,
            label_count,
        )
        return task_id

    def _load_selections(self, task_id: str) -> int:
        path = self._data_dir / "selections.json"
        with open(path) as f:
            raw_list = json.load(f)
        return self._raw_data_repo.save_raw_selections(task_id, raw_list)

    def _load_odds(self, task_id: str) -> int:
        path = self._data_dir / "odds.csv"
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        return self._raw_data_repo.save_raw_odds(task_id, rows)

    def _load_labels(self, task_id: str) -> int:
        path = self._data_dir / "labels.csv"
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        return self._raw_data_repo.save_raw_labels(task_id, rows)
