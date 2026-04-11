import logging

from app.worker import celery_app
from app.worker_dependencies import (
    build_pipeline_service,
    ensure_mysql_tables,
    get_mongo_database,
    get_mysql_session,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="pipeline.process_analysis", bind=True, max_retries=1)
def process_analysis(self, task_id: str) -> None:
    """Celery task — 정제 파이프라인 실행 (inbound adapter)

    비즈니스 로직은 PipelineService에 위임한다.
    """
    logger.info("파이프라인 시작: task_id=%s", task_id)

    db = get_mongo_database()
    session = get_mysql_session()
    ensure_mysql_tables()

    try:
        service = build_pipeline_service(db, session)
        service.execute(task_id)
        session.commit()
        logger.info("파이프라인 완료: task_id=%s", task_id)

    except Exception as e:
        session.rollback()
        logger.exception("파이프라인 실패: task_id=%s", task_id)
        raise self.retry(exc=e, countdown=10) from e

    finally:
        session.close()
