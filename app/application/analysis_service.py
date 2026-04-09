import itertools
import logging
from collections.abc import Callable, Iterator
from pathlib import Path

from app.application.file_loaders import FileLoaderProvider
from app.domain.models import AnalyzeTask
from app.domain.ports import IdGenerator, RawDataRepository, TaskDispatcher, TaskRepository

logger = logging.getLogger(__name__)

CHUNK_SIZE = 5000


class AnalysisService:
    """분석 요청 접수 서비스 (Command) -- 파일 -> MongoDB 적재 + 비동기 작업 발행"""

    def __init__(
        self,
        raw_data_repo: RawDataRepository,
        task_repo: TaskRepository,
        task_dispatcher: TaskDispatcher,
        id_generator: IdGenerator,
        loader_provider: FileLoaderProvider,
        data_dir: Path,
    ) -> None:
        self._raw_data_repo = raw_data_repo
        self._task_repo = task_repo
        self._task_dispatcher = task_dispatcher
        self._id_generator = id_generator
        self._loader_provider = loader_provider
        self._data_dir = data_dir

    def submit(self) -> str:
        """3개 파일을 MongoDB에 적재하고 비동기 정제 작업을 발행한다."""
        task_id = self._id_generator.generate()

        sel_path = self._data_dir / "selections.json"
        odd_path = self._data_dir / "odds.csv"
        label_path = self._data_dir / "labels.csv"

        sel_count = self._load_and_save(sel_path, task_id, self._raw_data_repo.save_raw_selections)
        odd_count = self._load_and_save(odd_path, task_id, self._raw_data_repo.save_raw_odds)
        label_count = self._load_and_save(label_path, task_id, self._raw_data_repo.save_raw_labels)

        task = AnalyzeTask.create_new(
            task_id=task_id,
            selection_count=sel_count,
            odd_count=odd_count,
            label_count=label_count,
        )
        self._task_repo.create(task)

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
        path: Path,
        task_id: str,
        save_fn: Callable[[str, list[dict]], int],
    ) -> int:
        """파일 확장자에서 로더를 자동 감지하여 청크 단위로 MongoDB에 적재한다."""
        loader = self._loader_provider.resolve(path)
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
