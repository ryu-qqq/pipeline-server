import logging
from datetime import datetime, timedelta

from app.domain.enums import OutboxStatus
from app.domain.models import OutboxCriteria
from app.domain.ports import OutboxRepository, TaskDispatcher

logger = logging.getLogger(__name__)

DEFAULT_FETCH_LIMIT = 10
DEFAULT_ZOMBIE_THRESHOLD_MINUTES = 5
DEFAULT_ZOMBIE_LIMIT = 50


class OutboxRelayService:
    """Outbox 메시지를 폴링하여 실제 발행하는 서비스 (Command)"""

    def __init__(
        self,
        outbox_repo: OutboxRepository,
        task_dispatcher: TaskDispatcher,
        fetch_limit: int = DEFAULT_FETCH_LIMIT,
    ) -> None:
        self._outbox_repo = outbox_repo
        self._task_dispatcher = task_dispatcher
        self._fetch_limit = fetch_limit

    def relay(self) -> int:
        """PENDING 메시지를 읽어 발행한다.

        흐름: 조회 → PROCESSING 전환 → 발행 → PUBLISHED 전환
        발행 실패 시 PROCESSING 상태로 남겨 좀비 스케줄러가 복구한다.

        낙관적 잠금: PROCESSING→PUBLISHED 전환 시 save_if_status를 사용하여
        recover_zombies()가 동시에 상태를 변경한 경우 덮어쓰지 않는다.

        Returns:
            발행에 성공한 건수
        """
        criteria = OutboxCriteria(status=OutboxStatus.PENDING, limit=self._fetch_limit)
        messages = self._outbox_repo.find_by(criteria)
        published = 0

        for msg in messages:
            msg = msg.mark_processing()
            self._outbox_repo.save(msg)

            try:
                if msg.message_type == "ANALYZE":
                    self._task_dispatcher.dispatch(msg.payload["task_id"])

                published_msg = msg.mark_published()
                updated = self._outbox_repo.save_if_status(published_msg, OutboxStatus.PROCESSING)
                if updated:
                    published += 1
                else:
                    logger.warning("Outbox 상태 변경 스킵 (이미 다른 프로세스가 처리): message_id=%s", msg.message_id)

            except Exception:
                logger.exception("Outbox 발행 실패: message_id=%s", msg.message_id)

        return published

    def recover_zombies(self, threshold_minutes: int = DEFAULT_ZOMBIE_THRESHOLD_MINUTES) -> int:
        """PROCESSING 상태로 일정 시간 이상 방치된 좀비 메시지를 복구한다.

        재시도 가능하면 PENDING으로 되돌리고, 초과하면 FAILED로 처리한다.

        낙관적 잠금: save_if_status로 PROCESSING 상태인 경우에만 저장하여
        relay()가 이미 PUBLISHED로 전환한 메시지를 덮어쓰지 않는다.

        Returns:
            복구된 건수
        """
        cutoff = datetime.now() - timedelta(minutes=threshold_minutes)
        criteria = OutboxCriteria(status=OutboxStatus.PROCESSING, before=cutoff, limit=DEFAULT_ZOMBIE_LIMIT)
        zombies = self._outbox_repo.find_by(criteria)
        recovered = 0

        for msg in zombies:
            try:
                msg = msg.with_retry_incremented()

                if msg.is_retriable():
                    msg = msg.back_to_pending()
                    logger.warning("좀비 복구 → PENDING: message_id=%s, retry=%d", msg.message_id, msg.retry_count)
                else:
                    msg = msg.mark_failed()
                    logger.warning("좀비 최종 실패: message_id=%s, retry=%d", msg.message_id, msg.retry_count)

                updated = self._outbox_repo.save_if_status(msg, OutboxStatus.PROCESSING)
                if updated:
                    recovered += 1
                else:
                    logger.warning("좀비 복구 스킵 (이미 다른 프로세스가 처리): message_id=%s", msg.message_id)

            except Exception:
                logger.exception("좀비 복구 실패: message_id=%s", msg.message_id)

        return recovered
