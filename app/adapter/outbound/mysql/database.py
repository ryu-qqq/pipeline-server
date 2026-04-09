import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://pipeline:pipeline@localhost:3306/pipeline?charset=utf8mb4",
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def create_tables() -> None:
    """모든 테이블을 생성한다."""
    Base.metadata.create_all(bind=engine)


def drop_tables() -> None:
    """모든 테이블을 삭제한다. (재분석 시 사용)"""
    Base.metadata.drop_all(bind=engine)


def get_session() -> Session:
    """새 DB 세션을 반환한다."""
    return SessionLocal()
