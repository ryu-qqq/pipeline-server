import logging

from app.adapter.outbound.database import SessionLocal, create_tables
from app.adapter.outbound.mongo_repositories import MongoRawDataRepository, MongoTaskRepository
from app.adapter.outbound.mongodb import get_mongo_db
from app.adapter.outbound.redis_client import invalidate_search_cache
from app.adapter.outbound.repositories import (
    SqlLabelRepository,
    SqlOddTagRepository,
    SqlRejectionRepository,
    SqlSelectionRepository,
)
from app.application.pipeline_service import PipelineService
from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="pipeline.process_analysis", bind=True, max_retries=1)
def process_analysis(self, task_id: str) -> None:
    """Celery task — 정제 파이프라인 실행 (inbound adapter)

    MongoDB에서 원본 데이터를 읽어 정제 후 MySQL에 적재한다.
    비즈니스 로직은 PipelineService에 위임한다.
    """
    logger.info("파이프라인 시작: task_id=%s", task_id)

    db = get_mongo_db()
    session = SessionLocal()
    create_tables()

    try:
        service = PipelineService(
            raw_data_repo=MongoRawDataRepository(db),
            task_repo=MongoTaskRepository(db),
            selection_repo=SqlSelectionRepository(session),
            odd_tag_repo=SqlOddTagRepository(session),
            label_repo=SqlLabelRepository(session),
            rejection_repo=SqlRejectionRepository(session),
        )

        service.execute(task_id)
        session.commit()

        # 정제 완료 → 검색 캐시 무효화 (데이터가 변경됐으므로)
        invalidate_search_cache()

        logger.info("파이프라인 완료: task_id=%s", task_id)

    except Exception as e:
        session.rollback()
        logger.exception("파이프라인 실패: task_id=%s", task_id)
        raise self.retry(exc=e, countdown=10) from e

    finally:
        session.close()
