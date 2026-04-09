import itertools
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.application.file_loaders import FileLoaderProvider
from app.domain.ports import RawDataRepository

logger = logging.getLogger(__name__)

CHUNK_SIZE = 5000


@dataclass(frozen=True)
class IngestionResult:
    """파일 적재 결과"""

    task_id: str
    selection_count: int
    odd_count: int
    label_count: int


class IngestionService:
    """파일 적재 서비스 — 파일 읽기 → MongoDB 적재 (저장 책임)"""

    def __init__(
        self,
        raw_data_repo: RawDataRepository,
        loader_provider: FileLoaderProvider,
        data_dir: Path,
    ) -> None:
        self._raw_data_repo = raw_data_repo
        self._loader_provider = loader_provider
        self._data_dir = data_dir

    def ingest(self, task_id: str) -> IngestionResult:
        """3개 파일을 청크 단위로 MongoDB에 적재한다."""
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
            chunk = list(itertools.islice(it, CHUNK_SIZE))
            if not chunk:
                break
            total += save_fn(task_id, chunk)
        return total
