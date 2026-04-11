import logging

from app.domain.exceptions import DomainError
from app.worker import celery_app
from app.worker_dependencies import (
    build_pipeline_service,
    ensure_mysql_tables,
    get_mongo_database,
    get_mysql_session,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="pipeline.process_analysis", bind=True, max_retries=3)
def process_analysis(self, task_id: str) -> None:
    """Celery task — 정제 파이프라인 실행 (inbound adapter)

    비즈니스 로직은 PipelineService에 위임한다.
    DomainError(데이터 검증 실패)는 재시도하지 않고, 인프라 오류만 지수 백오프로 재시도한다.
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

    except DomainError as e:
        session.rollback()
        logger.error("데이터 검증 실패 (재시도 불가): task_id=%s, error=%s", task_id, e)

    except Exception as e:
        session.rollback()
        logger.exception(
            "파이프라인 실패 (재시도 %d/%d): task_id=%s",
            self.request.retries, self.max_retries, task_id,
        )
        raise self.retry(exc=e, countdown=10 * (2 ** self.request.retries)) from e

    finally:
        session.close()
