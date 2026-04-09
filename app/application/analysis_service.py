import itertools
import logging
from collections.abc import Callable, Iterator
from pathlib import Path

from app.application.file_loaders import CsvFileLoader, FileLoader, JsonFileLoader
from app.domain.models import AnalyzeTask
from app.domain.ports import IdGenerator, RawDataRepository, TaskDispatcher, TaskRepository

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
        id_generator: IdGenerator,
        data_dir: Path,
    ) -> None:
        self._raw_data_repo = raw_data_repo
        self._task_repo = task_repo
        self._task_dispatcher = task_dispatcher
        self._id_generator = id_generator
        self._data_dir = data_dir

        # FileLoader 전략 -- 상태 없는 순수 전략이므로 내부 생성
        self._json_loader: FileLoader = JsonFileLoader()
        self._odd_loader: FileLoader = CsvFileLoader(REQUIRED_ODD_HEADERS)
        self._label_loader: FileLoader = CsvFileLoader(REQUIRED_LABEL_HEADERS)

    def submit(self) -> str:
        """3개 파일을 MongoDB에 적재하고 비동기 정제 작업을 발행한다."""
        task_id = self._id_generator.generate()

        sel_path = self._data_dir / "selections.json"
        odd_path = self._data_dir / "odds.csv"
        label_path = self._data_dir / "labels.csv"

        sel_count = self._load_and_save(self._json_loader, sel_path, task_id, self._raw_data_repo.save_raw_selections)
        odd_count = self._load_and_save(self._odd_loader, odd_path, task_id, self._raw_data_repo.save_raw_odds)
        label_count = self._load_and_save(self._label_loader, label_path, task_id, self._raw_data_repo.save_raw_labels)

        task = AnalyzeTask.create_new(
            task_id=task_id,
            selection_count=sel_count,
            odd_count=odd_count,
            label_count=label_count,
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

    def _load_and_save(
        self,
        loader: FileLoader,
        path: Path,
        task_id: str,
        save_fn: Callable[[str, list[dict]], int],
    ) -> int:
        """FileLoader로 데이터를 읽고 청크 단위로 MongoDB에 적재한다."""
        records = loader.load(path)
        total = 0
        for chunk in self._chunked(records, CHUNK_SIZE):
            total += save_fn(task_id, chunk)
        return total

    @staticmethod
    def _chunked(iterable: Iterator[dict], size: int) -> Iterator[list[dict]]:
        """Iterator를 size 단위로 잘라 list 청크를 yield한다."""
        it = iter(iterable)
        while True:
            chunk = list(itertools.islice(it, size))
            if not chunk:
                break
            yield chunk
