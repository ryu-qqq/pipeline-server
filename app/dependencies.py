import os
from collections.abc import Generator
from pathlib import Path

from fastapi import Depends
from sqlalchemy.orm import Session

from app.adapter.outbound.database import SessionLocal
from app.adapter.outbound.repositories import (
    SqlLabelRepository,
    SqlOddTagRepository,
    SqlRejectionRepository,
    SqlSearchRepository,
    SqlSelectionRepository,
)
from app.application.analysis_service import AnalysisService
from app.application.rejection_service import RejectionService
from app.application.search_service import SearchService
from app.domain.ports import (
    LabelRepository,
    OddTagRepository,
    RejectionRepository,
    SearchRepository,
    SelectionRepository,
)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


def get_db_session() -> Generator[Session, None, None]:
    """요청 단위 DB 세션을 관리한다. (= Spring @Transactional)"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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


def get_analysis_service(
    selection_repo: SelectionRepository = Depends(get_selection_repo),
    odd_tag_repo: OddTagRepository = Depends(get_odd_tag_repo),
    label_repo: LabelRepository = Depends(get_label_repo),
    rejection_repo: RejectionRepository = Depends(get_rejection_repo),
) -> AnalysisService:
    return AnalysisService(
        selection_repo=selection_repo,
        odd_tag_repo=odd_tag_repo,
        label_repo=label_repo,
        rejection_repo=rejection_repo,
        data_dir=DATA_DIR,
    )


def get_rejection_service(
    rejection_repo: RejectionRepository = Depends(get_rejection_repo),
) -> RejectionService:
    return RejectionService(rejection_repo=rejection_repo)


def get_search_service(
    search_repo: SearchRepository = Depends(get_search_repo),
) -> SearchService:
    return SearchService(search_repo=search_repo)
