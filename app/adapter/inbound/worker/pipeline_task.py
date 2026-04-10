import logging

from app.adapter.outbound.mongodb.client import get_mongo_db
from app.adapter.outbound.mongodb.repositories import MongoRawDataRepository, MongoTaskRepository
from app.adapter.outbound.mysql.database import SessionLocal, create_tables
from app.adapter.outbound.mysql.repositories import (
    SqlLabelRepository,
    SqlOddTagRepository,
    SqlRejectionRepository,
    SqlSelectionRepository,
)
from app.adapter.outbound.redis.client import get_redis
from app.adapter.outbound.redis.repositories import RedisCacheRepository
from app.application.phase_runners import (
    LabelPhaseRunner,
    OddTagPhaseRunner,
    PhaseRunnerProvider,
    SelectionPhaseRunner,
)
from app.application.pipeline_service import PipelineService
from app.domain.enums import Stage
from app.worker import celery_app

logger = logging.getLogger(__name__)


def _build_pipeline_service(db, session) -> PipelineService:
    """Worker 진입점 전용 DI 조립"""
    raw_data_repo = MongoRawDataRepository(db)
    task_repo = MongoTaskRepository(db)
    rejection_repo = SqlRejectionRepository(session)
    selection_repo = SqlSelectionRepository(session)
    odd_tag_repo = SqlOddTagRepository(session)
    label_repo = SqlLabelRepository(session)

    provider = PhaseRunnerProvider()
    provider.register(Stage.SELECTION, SelectionPhaseRunner(
        raw_data_repo=raw_data_repo,
        task_repo=task_repo,
        rejection_repo=rejection_repo,
        selection_repo=selection_repo,
    ))
    provider.register(Stage.ODD_TAGGING, OddTagPhaseRunner(
        raw_data_repo=raw_data_repo,
        task_repo=task_repo,
        rejection_repo=rejection_repo,
        odd_tag_repo=odd_tag_repo,
    ))
    provider.register(Stage.AUTO_LABELING, LabelPhaseRunner(
        raw_data_repo=raw_data_repo,
        task_repo=task_repo,
        rejection_repo=rejection_repo,
        label_repo=label_repo,
    ))

    return PipelineService(
        task_repo=task_repo,
        selection_repo=selection_repo,
        odd_tag_repo=odd_tag_repo,
        label_repo=label_repo,
        cache_repo=RedisCacheRepository(get_redis()),
        phase_runner_provider=provider,
    )


@celery_app.task(name="pipeline.process_analysis", bind=True, max_retries=1)
def process_analysis(self, task_id: str) -> None:
    """Celery task — 정제 파이프라인 실행 (inbound adapter)

    비즈니스 로직은 PipelineService에 위임한다.
    """
    logger.info("파이프라인 시작: task_id=%s", task_id)

    db = get_mongo_db()
    session = SessionLocal()
    create_tables()

    try:
        service = _build_pipeline_service(db, session)
        service.execute(task_id)
        session.commit()
        logger.info("파이프라인 완료: task_id=%s", task_id)

    except Exception as e:
        session.rollback()
        logger.exception("파이프라인 실패: task_id=%s", task_id)
        raise self.retry(exc=e, countdown=10) from e

    finally:
        session.close()
