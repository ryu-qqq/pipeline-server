import logging

from app.adapter.outbound.celery.dispatcher import CeleryTaskDispatcher
from app.adapter.outbound.mongodb.client import get_mongo_db
from app.adapter.outbound.mongodb.repositories import MongoOutboxRepository
from app.application.outbox_relay import OutboxRelayService
from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="outbox.relay")
def relay_outbox_messages() -> None:
    """5초마다 실행 — Outbox에서 PENDING 메시지를 꺼내 발행한다."""
    db = get_mongo_db()
    service = OutboxRelayService(
        outbox_repo=MongoOutboxRepository(db),
        task_dispatcher=CeleryTaskDispatcher(),
    )
    published = service.relay()
    if published > 0:
        logger.info("Outbox relay: %d건 발행", published)
