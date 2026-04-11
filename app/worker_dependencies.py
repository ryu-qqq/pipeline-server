"""Worker 전용 DI 조립 모듈

Celery Worker는 FastAPI Depends() 체인을 사용할 수 없으므로,
dependencies.py와 동일한 역할을 수동으로 수행한다.

이 모듈은 dependencies.py처럼 app/ 루트에 위치하여
inbound/worker가 outbound 구현체를 직접 참조하지 않도록 분리한다.
"""

from pymongo.database import Database
from sqlalchemy.orm import Session

from app.adapter.outbound.celery.dispatcher import CeleryTaskDispatcher
from app.adapter.outbound.mongodb.client import get_mongo_db
from app.adapter.outbound.mongodb.repositories import (
    MongoOutboxRepository,
    MongoRawDataRepository,
    MongoTaskRepository,
)
from app.adapter.outbound.mysql.database import SessionLocal, create_tables
from app.adapter.outbound.mysql.repositories import (
    SqlLabelRepository,
    SqlOddTagRepository,
    SqlRejectionRepository,
    SqlSelectionRepository,
)
from app.application.outbox_relay_service import OutboxRelayService
from app.application.phase_runners import (
    LabelPhaseRunner,
    OddTagPhaseRunner,
    PhaseRunnerProvider,
    SelectionPhaseRunner,
)
from app.application.pipeline_service import PipelineService
from app.domain.enums import Stage


def build_pipeline_service(db: Database, session: Session) -> PipelineService:
    """Worker 진입점 전용 PipelineService 조립"""
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
        phase_runner_provider=provider,
    )


def build_relay_service() -> OutboxRelayService:
    """Worker 진입점 전용 OutboxRelayService 조립"""
    db = get_mongo_db()
    return OutboxRelayService(
        outbox_repo=MongoOutboxRepository(db),
        task_dispatcher=CeleryTaskDispatcher(),
    )


def get_mongo_database() -> Database:
    """MongoDB 데이터베이스를 반환한다."""
    return get_mongo_db()


def get_mysql_session() -> Session:
    """MySQL 세션을 반환한다."""
    return SessionLocal()


def ensure_mysql_tables() -> None:
    """MySQL 테이블을 생성한다."""
    create_tables()
