import logging
from collections.abc import Callable
from pathlib import Path

from app.application.file_loaders import FileLoaderProvider
from app.domain.models import AnalyzeTask
from app.domain.ports import IdGenerator, RawDataRepository

logger = logging.getLogger(__name__)

CHUNK_SIZE = 5000


class AnalyzeTaskFactory:
    """AnalyzeTask를 생성하는 팩토리

    ID 생성 + 파일 적재(MongoDB) + 도메인 객체 조립을 담당한다.
    서비스는 이 팩토리를 호출하고, 저장/발행만 조율한다.
    """

    def __init__(
        self,
        id_generator: IdGenerator,
        raw_data_repo: RawDataRepository,
        loader_provider: FileLoaderProvider,
        data_dir: Path,
    ) -> None:
        self._id_generator = id_generator
        self._raw_data_repo = raw_data_repo
        self._loader_provider = loader_provider
        self._data_dir = data_dir

    def create(self) -> AnalyzeTask:
        """3개 파일을 MongoDB에 적재하고 AnalyzeTask를 생성한다."""
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
            "AnalyzeTask 생성: task_id=%s, selections=%d, odds=%d, labels=%d",
            task_id,
            sel_count,
            odd_count,
            label_count,
        )

        return AnalyzeTask.create_new(
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
        """파일 확장자에서 로더를 자동 감지하여 청크 단위로 MongoDB에 적재한다."""
        import itertools

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
