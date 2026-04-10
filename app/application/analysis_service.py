import logging

from app.application.analyze_task_factory import AnalyzeTaskFactory
from app.application.data_ingestor import DataIngestor
from app.application.decorators import transactional
from app.domain.ports import OutboxRepository, TaskRepository, TransactionManager

logger = logging.getLogger(__name__)


class AnalysisService:
    """분석 요청 접수 서비스 (Command) — 적재 → 생성 → 저장 조율"""

    def __init__(
        self,
        data_ingestor: DataIngestor,
        task_factory: AnalyzeTaskFactory,
        task_repo: TaskRepository,
        outbox_repo: OutboxRepository,
        tx_manager: TransactionManager,
    ) -> None:
        self._data_ingestor = data_ingestor
        self._task_factory = task_factory
        self._task_repo = task_repo
        self._outbox_repo = outbox_repo
        self._tx_manager = tx_manager

    @transactional
    def submit(self) -> str:
        """3개 파일을 MongoDB에 적재하고 Outbox에 이벤트를 저장한다.

        @transactional: 적재 + Task 저장 + Outbox 저장을
        하나의 트랜잭션으로 묶어 부분 실패 시 전체 롤백을 보장한다.
        """
        ingestion = self._data_ingestor.ingest()
        bundle = self._task_factory.create(ingestion)

        self._task_repo.create(bundle.task)
        self._outbox_repo.save(bundle.outbox)

        logger.info("분석 접수: task_id=%s", ingestion.task_id)
        return ingestion.task_id
