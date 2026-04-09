import logging

from app.application.analyze_task_factory import AnalyzeTaskFactory
from app.application.ingestion_service import IngestionService
from app.domain.ports import IdGenerator, OutboxRepository, TaskRepository

logger = logging.getLogger(__name__)


class AnalysisService:
    """분석 요청 접수 서비스 (Command) — 적재 → 생성 → 저장 조율"""

    def __init__(
        self,
        id_generator: IdGenerator,
        ingestion_service: IngestionService,
        task_factory: AnalyzeTaskFactory,
        task_repo: TaskRepository,
        outbox_repo: OutboxRepository,
    ) -> None:
        self._id_generator = id_generator
        self._ingestion_service = ingestion_service
        self._task_factory = task_factory
        self._task_repo = task_repo
        self._outbox_repo = outbox_repo

    def submit(self) -> str:
        """3개 파일을 MongoDB에 적재하고 Outbox에 이벤트를 저장한다."""
        task_id = self._id_generator.generate()

        # 1. 적재 (IngestionService — 파일 → MongoDB)
        ingestion = self._ingestion_service.ingest(task_id)

        # 2. 생성 (Factory — 순수 객체 조립, 저장소 모름)
        bundle = self._task_factory.create(ingestion)

        # 3. 저장 (같은 MongoDB에 순서대로)
        self._task_repo.create(bundle.task)
        self._outbox_repo.save(bundle.outbox)

        logger.info("분석 접수: task_id=%s", task_id)
        return task_id
