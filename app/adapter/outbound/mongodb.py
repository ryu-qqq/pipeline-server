import os

from pymongo import MongoClient
from pymongo.database import Database

MONGO_URL = os.getenv(
    "MONGO_URL",
    "mongodb://pipeline:pipeline@localhost:27017/pipeline?authSource=admin",
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


def ensure_indexes() -> None:
    """MongoDB 인덱스를 생성한다."""
    db = get_mongo_db()
    db.raw_data.create_index([("task_id", 1), ("source", 1)])
    db.analyze_tasks.create_index([("status", 1)])
