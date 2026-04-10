from collections.abc import Iterator
from datetime import datetime

from pymongo.database import Database

from app.adapter.outbound.mongodb.documents import AnalyzeTaskDocument, OutboxDocument, RawDataDocument
from app.adapter.outbound.mongodb.mappers import OutboxDocumentMapper, TaskDocumentMapper
from app.adapter.outbound.mongodb.transaction import get_current_session
from app.domain.enums import Stage, TaskStatus
from app.domain.models import AnalyzeTask, OutboxCriteria, OutboxMessage
from app.domain.ports import OutboxRepository, RawDataRepository, TaskRepository
from app.domain.value_objects import StageProgress

DEFAULT_BULK_INSERT_SIZE = 5000


class MongoRawDataRepository(RawDataRepository):
    """MongoDB 원본 데이터 저장소 구현체"""

    def __init__(self, db: Database, bulk_insert_size: int = DEFAULT_BULK_INSERT_SIZE) -> None:
        self._collection = db.raw_data
        self._bulk_insert_size = bulk_insert_size

    def save_raw_selections(self, task_id: str, raw_list: list[dict]) -> int:
        return self._bulk_save(task_id, "selections", raw_list)

    def save_raw_odds(self, task_id: str, rows: list[dict]) -> int:
        return self._bulk_save(task_id, "odds", rows)

    def save_raw_labels(self, task_id: str, rows: list[dict]) -> int:
        return self._bulk_save(task_id, "labels", rows)

    def find_by_task_and_source(self, task_id: str, source: str) -> Iterator[dict]:
        cursor = self._collection.find(
            {"task_id": task_id, "source": source},
            {"_id": 0, "data": 1},
        )
        for doc in cursor:
            yield doc["data"]

    def delete_by_task(self, task_id: str) -> None:
        self._collection.delete_many({"task_id": task_id}, session=get_current_session())

    def _bulk_save(self, task_id: str, source: str, items: list[dict]) -> int:
        total = 0
        now = datetime.now()
        for i in range(0, len(items), self._bulk_insert_size):
            chunk = items[i : i + self._bulk_insert_size]
            docs = [
                RawDataDocument(task_id=task_id, source=source, data=item, created_at=now).to_dict() for item in chunk
            ]
            self._collection.insert_many(docs, session=get_current_session())
            total += len(chunk)
        return total


class MongoTaskRepository(TaskRepository):
    """MongoDB 분석 작업 상태 저장소 구현체"""

    def __init__(self, db: Database) -> None:
        self._collection = db.analyze_tasks

    def save(self, task: AnalyzeTask) -> None:
        document = TaskDocumentMapper.to_document(task)
        self._collection.replace_one(
            {"_id": task.task_id},
            document.to_dict(),
            upsert=True,
            session=get_current_session(),
        )

    def find_by_id(self, task_id: str) -> AnalyzeTask | None:
        doc = self._collection.find_one({"_id": task_id})
        if not doc:
            return None
        task_doc = AnalyzeTaskDocument.from_dict(doc)
        return TaskDocumentMapper.to_domain(task_doc)

    def find_by_statuses(self, statuses: list[TaskStatus]) -> AnalyzeTask | None:
        doc = self._collection.find_one(
            {"status": {"$in": [s.value for s in statuses]}},
            sort=[("created_at", -1)],
        )
        if not doc:
            return None
        task_doc = AnalyzeTaskDocument.from_dict(doc)
        return TaskDocumentMapper.to_domain(task_doc)


class MongoOutboxRepository(OutboxRepository):
    """MongoDB Outbox 저장소 구현체"""

    def __init__(self, db: Database) -> None:
        self._collection = db.outbox

    def save(self, message: OutboxMessage) -> None:
        document = OutboxDocumentMapper.to_document(message)
        self._collection.replace_one(
            {"_id": message.message_id},
            document.to_dict(),
            upsert=True,
            session=get_current_session(),
        )

    def find_by(self, criteria: OutboxCriteria) -> list[OutboxMessage]:
        query: dict = {"status": criteria.status.value}
        if criteria.before is not None:
            query["updated_at"] = {"$lt": criteria.before}

        cursor = (
            self._collection.find(query)
            .sort("created_at", 1)
            .limit(criteria.limit)
        )
        return [OutboxDocumentMapper.to_domain(OutboxDocument.from_dict(doc)) for doc in cursor]
