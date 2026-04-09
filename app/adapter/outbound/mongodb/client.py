import os
from collections.abc import Generator
from contextlib import contextmanager

from pymongo import MongoClient
from pymongo.client_session import ClientSession
from pymongo.database import Database

MONGO_URL = os.getenv(
    "MONGO_URL",
    "mongodb://pipeline:pipeline@localhost:27017/pipeline?authSource=admin&replicaSet=rs0",
)

_client: MongoClient | None = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URL)
    return _client


def get_mongo_db() -> Database:
    client = get_mongo_client()
    return client.get_database("pipeline")


@contextmanager
def mongo_transaction() -> Generator[ClientSession, None, None]:
    """MongoDB 트랜잭션 세션을 제공하는 context manager.

    with mongo_transaction() as session:
        collection.insert_one(doc, session=session)
        collection2.insert_one(doc2, session=session)
    # 블록 끝 → 자동 커밋. 예외 시 자동 롤백.
    """
    client = get_mongo_client()
    with client.start_session() as session, session.start_transaction():
        yield session


def ensure_indexes() -> None:
    """MongoDB 인덱스를 생성한다."""
    db = get_mongo_db()
    db.raw_data.create_index([("task_id", 1), ("source", 1)])
    db.analyze_tasks.create_index([("status", 1)])
    db.outbox.create_index([("status", 1), ("created_at", 1)])
