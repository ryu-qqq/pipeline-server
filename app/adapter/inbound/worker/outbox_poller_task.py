import logging

from app.worker import celery_app
from app.worker_dependencies import build_relay_service

logger = logging.getLogger(__name__)


@celery_app.task(name="outbox.relay")
def relay_outbox_messages() -> None:
    """5초마다 실행 — Outbox에서 PENDING 메시지를 꺼내 발행한다."""
    service = build_relay_service()
    published = service.relay()
    if published > 0:
        logger.info("Outbox relay: %d건 발행", published)


@celery_app.task(name="outbox.recover_zombies")
def recover_zombie_messages() -> None:
    """1분마다 실행 — PROCESSING 상태로 방치된 좀비 메시지를 복구한다."""
    service = build_relay_service()
    recovered = service.recover_zombies()
    if recovered > 0:
        logger.info("좀비 복구: %d건", recovered)
