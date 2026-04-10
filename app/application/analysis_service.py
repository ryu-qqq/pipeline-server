import logging

from app.application.data_ingestor import DataIngestor
from app.application.decorators import transactional
from app.domain.enums import TaskStatus
from app.domain.exceptions import ConflictError
from app.domain.models import AnalyzeTask, OutboxMessage
from app.domain.ports import IdGenerator, OutboxRepository, TaskRepository, TransactionManager

logger = logging.getLogger(__name__)


class AnalysisService:
    """분석 요청 접수 서비스 (Command) — 적재 → Task/Outbox 생성 → 저장"""

    def __init__(
        self,
        data_ingestor: DataIngestor,
        id_generator: IdGenerator,
        task_repo: TaskRepository,
        outbox_repo: OutboxRepository,
        tx_manager: TransactionManager,
    ) -> None:
        self._data_ingestor = data_ingestor
        self._id_generator = id_generator
        self._task_repo = task_repo
        self._outbox_repo = outbox_repo
        self._tx_manager = tx_manager

    @transactional
    def submit(self) -> str:
        """3개 파일을 MongoDB에 적재하고 Outbox에 이벤트를 저장한다.

        @transactional: 적재 + Task 저장 + Outbox 저장을
        하나의 트랜잭션으로 묶어 부분 실패 시 전체 롤백을 보장한다.
        """
        active = self._task_repo.find_by_statuses([TaskStatus.PENDING, TaskStatus.PROCESSING])
        if active is not None:
            raise ConflictError(f"이미 진행 중인 작업이 있습니다: {active.task_id}")

        ingestion = self._data_ingestor.ingest()

        task = AnalyzeTask.create_new(
            task_id=ingestion.task_id,
            selection_count=ingestion.selection_count,
            odd_count=ingestion.odd_count,
            label_count=ingestion.label_count,
        )
        outbox = OutboxMessage.create_analyze_event(
            message_id=self._id_generator.generate(),
            task_id=ingestion.task_id,
        )

        self._task_repo.save(task)
        self._outbox_repo.save(outbox)

        logger.info("분석 접수: task_id=%s", ingestion.task_id)
        return ingestion.task_id
