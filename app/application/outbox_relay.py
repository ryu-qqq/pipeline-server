import logging

from app.domain.ports import OutboxRepository, TaskDispatcher

logger = logging.getLogger(__name__)


class OutboxRelayService:
    """Outbox 메시지를 폴링하여 실제 발행하는 서비스 (Command)"""

    PENDING_FETCH_LIMIT = 10

    def __init__(
        self,
        outbox_repo: OutboxRepository,
        task_dispatcher: TaskDispatcher,
    ) -> None:
        self._outbox_repo = outbox_repo
        self._task_dispatcher = task_dispatcher

    def relay(self) -> int:
        """PENDING 메시지를 읽어 발행하고 상태를 업데이트한다.

        Returns:
            발행에 성공한 건수
        """
        messages = self._outbox_repo.find_pending(limit=self.PENDING_FETCH_LIMIT)
        published = 0

        for msg in messages:
            try:
                if msg.message_type == "ANALYZE":
                    self._task_dispatcher.dispatch(msg.payload["task_id"])

                self._outbox_repo.mark_published(msg.message_id)
                published += 1

            except Exception:
                logger.exception("Outbox 발행 실패: message_id=%s", msg.message_id)
                self._outbox_repo.increment_retry(msg.message_id)
                if not msg.is_retriable():
                    self._outbox_repo.mark_failed(msg.message_id)

        return published
