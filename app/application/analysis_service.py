import csv
import itertools
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from app.domain.enums import TaskStatus
from app.domain.exceptions import DataNotFoundError, InvalidFormatError
from app.domain.ports import AnalyzeTask, RawDataRepository, StageProgress, TaskDispatcher, TaskRepository

logger = logging.getLogger(__name__)

REQUIRED_ODD_HEADERS = {"id", "video_id", "weather", "time_of_day", "road_surface"}
REQUIRED_LABEL_HEADERS = {"video_id", "object_class", "obj_count", "avg_confidence", "labeled_at"}

CHUNK_SIZE = 5000


class AnalysisService:
    """분석 요청 접수 서비스 (Command) -- 파일 -> MongoDB 적재 + 비동기 작업 발행"""

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

        # 비동기 작업 발행 -- Port를 통해 (Celery를 직접 모름)
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
        """JSON 파일을 파싱하고 청크 단위로 MongoDB에 적재한다.

        JSON은 전체 파싱이 불가피하지만, MongoDB 적재는 청크로 나눠서 메모리 부담을 줄인다.
        """
        path = self._data_dir / "selections.json"
        try:
            with open(path) as f:
                raw_list = json.load(f)
        except FileNotFoundError as err:
            raise DataNotFoundError(f"파일을 찾을 수 없습니다: {path}") from err
        except json.JSONDecodeError as e:
            raise InvalidFormatError(f"JSON 파싱 실패: {path} -- {e}") from e

        if not isinstance(raw_list, list):
            raise InvalidFormatError(f"selections.json은 배열이어야 합니다: {type(raw_list).__name__}")

        # 청크 단위로 MongoDB 적재
        total = 0
        for i in range(0, len(raw_list), CHUNK_SIZE):
            chunk = raw_list[i : i + CHUNK_SIZE]
            total += self._raw_data_repo.save_raw_selections(task_id, chunk)

        return total

    def _load_odds(self, task_id: str) -> int:
        """CSV 파일을 청크 단위로 읽어서 MongoDB에 적재한다."""
        path = self._data_dir / "odds.csv"
        return self._stream_csv(path, REQUIRED_ODD_HEADERS, task_id, "odds")

    def _load_labels(self, task_id: str) -> int:
        """CSV 파일을 청크 단위로 읽어서 MongoDB에 적재한다."""
        path = self._data_dir / "labels.csv"
        return self._stream_csv(path, REQUIRED_LABEL_HEADERS, task_id, "labels")

    def _stream_csv(self, path: Path, required_headers: set[str], task_id: str, source: str) -> int:
        """CSV를 itertools.islice로 청크 단위 읽기 -> MongoDB 적재.

        전체를 메모리에 올리지 않고 스트리밍 방식으로 처리한다.
        """
        try:
            f = open(path, newline="")  # noqa: SIM115
        except FileNotFoundError as err:
            raise DataNotFoundError(f"파일을 찾을 수 없습니다: {path}") from err

        with f:
            reader = csv.DictReader(f)

            # 헤더 검증 (첫 번째 청크 읽기 전에 수행)
            if reader.fieldnames is not None:
                actual_headers = set(reader.fieldnames)
                missing = required_headers - actual_headers
                if missing:
                    raise InvalidFormatError(f"CSV 필수 헤더 누락: {path} -- {sorted(missing)}")

            total = 0
            save_fn = self._raw_data_repo.save_raw_odds if source == "odds" else self._raw_data_repo.save_raw_labels

            while True:
                chunk = list(itertools.islice(reader, CHUNK_SIZE))
                if not chunk:
                    break

                # 첫 청크에서 헤더 검증 (fieldnames가 None인 경우 대비)
                if total == 0 and reader.fieldnames is None and chunk:
                    actual_headers = set(chunk[0].keys())
                    missing = required_headers - actual_headers
                    if missing:
                        raise InvalidFormatError(f"CSV 필수 헤더 누락: {path} -- {sorted(missing)}")

                total += save_fn(task_id, chunk)

        return total
