import os
from collections.abc import Generator
from pathlib import Path

from fastapi import Depends
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.adapter.outbound.identity.generator import UUIDv7Generator
from app.adapter.outbound.mongodb.client import get_mongo_client, get_mongo_db
from app.adapter.outbound.mongodb.repositories import MongoOutboxRepository, MongoRawDataRepository, MongoTaskRepository
from app.adapter.outbound.mongodb.transaction import MongoTransactionManager
from app.adapter.outbound.mysql.database import SessionLocal
from app.adapter.outbound.mysql.repositories import (
    SqlLabelRepository,
    SqlOddTagRepository,
    SqlRejectionRepository,
    SqlSearchRepository,
    SqlSelectionRepository,
)
from app.adapter.outbound.redis.client import get_redis
from app.adapter.outbound.redis.repositories import RedisCacheRepository
from app.application.analysis_service import AnalysisService
from app.application.analyze_task_factory import AnalyzeTaskFactory
from app.application.file_loaders import CsvFileLoader, FileLoaderProvider, JsonFileLoader
from app.application.ingestion_service import IngestionService
from app.application.rejection_service import RejectionService
from app.application.search_service import SearchService
from app.application.task_service import TaskService
from app.domain.enums import FileType
from app.domain.ports import (
    CacheRepository,
    IdGenerator,
    LabelRepository,
    OddTagRepository,
    OutboxRepository,
    RawDataRepository,
    RejectionRepository,
    SearchRepository,
    SelectionRepository,
    TaskRepository,
    TransactionManager,
)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


# === DB Session ===


def get_db_session() -> Generator[Session, None, None]:
    """요청 단위 MySQL 세션을 관리한다."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Database:
    """MongoDB 데이터베이스를 반환한다."""
    return get_mongo_db()


# === MySQL Repository ===


def get_selection_repo(session: Session = Depends(get_db_session)) -> SelectionRepository:
    return SqlSelectionRepository(session)


def get_odd_tag_repo(session: Session = Depends(get_db_session)) -> OddTagRepository:
    return SqlOddTagRepository(session)


def get_label_repo(session: Session = Depends(get_db_session)) -> LabelRepository:
    return SqlLabelRepository(session)


def get_rejection_repo(session: Session = Depends(get_db_session)) -> RejectionRepository:
    return SqlRejectionRepository(session)


def get_search_repo(session: Session = Depends(get_db_session)) -> SearchRepository:
    return SqlSearchRepository(session)


# === MongoDB Repository ===


def get_raw_data_repo(db: Database = Depends(get_db)) -> RawDataRepository:
    return MongoRawDataRepository(db)


def get_task_repo(db: Database = Depends(get_db)) -> TaskRepository:
    return MongoTaskRepository(db)


# === Outbox Repository ===


def get_outbox_repo(db: Database = Depends(get_db)) -> OutboxRepository:
    return MongoOutboxRepository(db)


# === Transaction Manager ===


def get_tx_manager() -> TransactionManager:
    """MongoDB 트랜잭션 매니저를 반환한다."""
    return MongoTransactionManager(get_mongo_client())


# === Redis Cache ===


def get_cache_repo() -> CacheRepository:
    return RedisCacheRepository(get_redis())


# === ID Generator ===


def get_id_generator() -> IdGenerator:
    return UUIDv7Generator()


# === FileLoader Provider ===


REQUIRED_ODD_HEADERS = {"id", "video_id", "weather", "time_of_day", "road_surface"}
REQUIRED_LABEL_HEADERS = {"video_id", "object_class", "obj_count", "avg_confidence", "labeled_at"}


def get_loader_provider() -> FileLoaderProvider:
    provider = FileLoaderProvider()
    provider.register(FileType.JSON, JsonFileLoader())
    provider.register(FileType.CSV, CsvFileLoader(REQUIRED_ODD_HEADERS | REQUIRED_LABEL_HEADERS))
    return provider


# === Ingestion Service ===


def get_ingestion_service(
    id_generator: IdGenerator = Depends(get_id_generator),
    raw_data_repo: RawDataRepository = Depends(get_raw_data_repo),
    loader_provider: FileLoaderProvider = Depends(get_loader_provider),
) -> IngestionService:
    return IngestionService(
        id_generator=id_generator,
        raw_data_repo=raw_data_repo,
        loader_provider=loader_provider,
        data_dir=DATA_DIR,
    )


# === Factory ===


def get_analyze_task_factory(
    id_generator: IdGenerator = Depends(get_id_generator),
) -> AnalyzeTaskFactory:
    return AnalyzeTaskFactory(id_generator=id_generator)


# === Service ===


def get_analysis_service(
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    task_factory: AnalyzeTaskFactory = Depends(get_analyze_task_factory),
    task_repo: TaskRepository = Depends(get_task_repo),
    outbox_repo: OutboxRepository = Depends(get_outbox_repo),
    tx_manager: TransactionManager = Depends(get_tx_manager),
) -> AnalysisService:
    return AnalysisService(
        ingestion_service=ingestion_service,
        task_factory=task_factory,
        task_repo=task_repo,
        outbox_repo=outbox_repo,
        tx_manager=tx_manager,
    )


def get_task_service(
    task_repo: TaskRepository = Depends(get_task_repo),
) -> TaskService:
    return TaskService(task_repo=task_repo)


def get_rejection_service(
    rejection_repo: RejectionRepository = Depends(get_rejection_repo),
) -> RejectionService:
    return RejectionService(rejection_repo=rejection_repo)


def get_search_service(
    search_repo: SearchRepository = Depends(get_search_repo),
    cache_repo: CacheRepository = Depends(get_cache_repo),
) -> SearchService:
    return SearchService(search_repo=search_repo, cache_repo=cache_repo)
