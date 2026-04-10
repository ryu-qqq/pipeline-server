import itertools
import logging
from collections.abc import Callable
from pathlib import Path

from app.application.file_loaders import FileLoaderProvider
from app.domain.ports import IdGenerator, RawDataRepository
from app.domain.value_objects import IngestionResult

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 5000


class DataIngestor:
    """파일 적재 서비스 — ID 생성 + 파일 읽기 → MongoDB 적재 (적재 책임)"""

    def __init__(
        self,
        id_generator: IdGenerator,
        raw_data_repo: RawDataRepository,
        loader_provider: FileLoaderProvider,
        data_dir: Path,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self._id_generator = id_generator
        self._raw_data_repo = raw_data_repo
        self._loader_provider = loader_provider
        self._data_dir = data_dir
        self._chunk_size = chunk_size

    def ingest(self) -> IngestionResult:
        """3개 파일을 청크 단위로 MongoDB에 적재한다."""
        task_id = self._id_generator.generate()

        sel_count = self._load_and_save(
            self._data_dir / "selections.json",
            task_id,
            self._raw_data_repo.save_raw_selections,
        )
        odd_count = self._load_and_save(
            self._data_dir / "odds.csv",
            task_id,
            self._raw_data_repo.save_raw_odds,
        )
        label_count = self._load_and_save(
            self._data_dir / "labels.csv",
            task_id,
            self._raw_data_repo.save_raw_labels,
        )

        logger.info(
            "파일 적재 완료: task_id=%s, selections=%d, odds=%d, labels=%d",
            task_id,
            sel_count,
            odd_count,
            label_count,
        )
        return IngestionResult(
            task_id=task_id,
            selection_count=sel_count,
            odd_count=odd_count,
            label_count=label_count,
        )

    def _load_and_save(
        self,
        path: Path,
        task_id: str,
        save_fn: Callable[[str, list[dict]], int],
    ) -> int:
        loader = self._loader_provider.resolve(path)
        records = loader.load(path)
        total = 0
        it = iter(records)
        while True:
            chunk = list(itertools.islice(it, self._chunk_size))
            if not chunk:
                break
            total += save_fn(task_id, chunk)
        return total
