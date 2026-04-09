import logging

from app.application.analyze_task_factory import AnalyzeTaskFactory
from app.domain.models import OutboxMessage
from app.domain.ports import IdGenerator, OutboxRepository, TaskRepository

logger = logging.getLogger(__name__)


class AnalysisService:
    """분석 요청 접수 서비스 (Command) — Outbox 패턴으로 신뢰성 있는 이벤트 발행"""

    def __init__(
        self,
        task_factory: AnalyzeTaskFactory,
        task_repo: TaskRepository,
        outbox_repo: OutboxRepository,
        id_generator: IdGenerator,
    ) -> None:
        self._task_factory = task_factory
        self._task_repo = task_repo
        self._outbox_repo = outbox_repo
        self._id_generator = id_generator

    def submit(self) -> str:
        """3개 파일을 MongoDB에 적재하고, Outbox에 이벤트를 저장한다.

        TaskDispatcher를 직접 호출하지 않고 Outbox 메시지를 남겨
        Relay가 폴링하여 비동기 발행하도록 한다.
        """
        task = self._task_factory.create()

        # MongoDB에 순서대로 저장 (같은 DB이므로 순서 보장)
        self._task_repo.create(task)

        # Outbox에 메시지 저장 (dispatcher 직접 호출 안 함)
        outbox = OutboxMessage.create_analyze_event(
            message_id=self._id_generator.generate(),
            task_id=task.task_id,
        )
        self._outbox_repo.save(outbox)

        logger.info("분석 접수 (Outbox): task_id=%s, outbox_id=%s", task.task_id, outbox.message_id)
        return task.task_id
