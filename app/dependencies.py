import os
from collections.abc import Generator
from pathlib import Path

from fastapi import Depends
from pymongo.database import Database
from sqlalchemy.orm import Session

from app.adapter.outbound.mongodb.client import get_mongo_db
from app.adapter.outbound.mongodb.repositories import MongoRawDataRepository, MongoTaskRepository
from app.adapter.outbound.mysql.database import SessionLocal
from app.adapter.outbound.mysql.repositories import (
    SqlLabelRepository,
    SqlOddTagRepository,
    SqlRejectionRepository,
    SqlSearchRepository,
    SqlSelectionRepository,
)
from app.application.analysis_service import AnalysisService
from app.application.rejection_service import RejectionService
from app.application.search_service import SearchService
from app.application.task_service import TaskService
from app.domain.ports import (
    LabelRepository,
    OddTagRepository,
    RawDataRepository,
    RejectionRepository,
    SearchRepository,
    SelectionRepository,
    TaskRepository,
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


# === Service ===


def get_analysis_service(
    raw_data_repo: RawDataRepository = Depends(get_raw_data_repo),
    task_repo: TaskRepository = Depends(get_task_repo),
) -> AnalysisService:
    return AnalysisService(
        raw_data_repo=raw_data_repo,
        task_repo=task_repo,
        data_dir=DATA_DIR,
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
) -> SearchService:
    return SearchService(search_repo=search_repo)
