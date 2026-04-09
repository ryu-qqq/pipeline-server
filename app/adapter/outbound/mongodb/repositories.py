from datetime import datetime

from pymongo.database import Database

from app.adapter.outbound.mongodb.documents import AnalyzeTaskDocument, RawDataDocument
from app.adapter.outbound.mongodb.mappers import TaskDocumentMapper
from app.domain.enums import Stage, TaskStatus
from app.domain.models import AnalyzeTask, StageProgress
from app.domain.ports import RawDataRepository, TaskRepository

BULK_INSERT_SIZE = 5000


class MongoRawDataRepository(RawDataRepository):
    """MongoDB 원본 데이터 저장소 구현체"""

    def __init__(self, db: Database) -> None:
        self._collection = db.raw_data

    def save_raw_selections(self, task_id: str, raw_list: list[dict]) -> int:
        return self._bulk_save(task_id, "selections", raw_list)

    def save_raw_odds(self, task_id: str, rows: list[dict]) -> int:
        return self._bulk_save(task_id, "odds", rows)

    def save_raw_labels(self, task_id: str, rows: list[dict]) -> int:
        return self._bulk_save(task_id, "labels", rows)

    def find_by_task_and_source(self, task_id: str, source: str) -> list[dict]:
        cursor = self._collection.find(
            {"task_id": task_id, "source": source},
            {"_id": 0, "data": 1},
        )
        return [doc["data"] for doc in cursor]

    def delete_by_task(self, task_id: str) -> None:
        self._collection.delete_many({"task_id": task_id})

    def _bulk_save(self, task_id: str, source: str, items: list[dict]) -> int:
        total = 0
        now = datetime.now()
        for i in range(0, len(items), BULK_INSERT_SIZE):
            chunk = items[i : i + BULK_INSERT_SIZE]
            docs = [
                RawDataDocument(task_id=task_id, source=source, data=item, created_at=now).to_dict() for item in chunk
            ]
            self._collection.insert_many(docs)
            total += len(chunk)
        return total


class MongoTaskRepository(TaskRepository):
    """MongoDB 분석 작업 상태 저장소 구현체"""

    def __init__(self, db: Database) -> None:
        self._collection = db.analyze_tasks

    def create(self, task: AnalyzeTask) -> None:
        document = TaskDocumentMapper.to_document(task)
        self._collection.insert_one(document.to_dict())

    def find_by_id(self, task_id: str) -> AnalyzeTask | None:
        doc = self._collection.find_one({"_id": task_id})
        if not doc:
            return None
        task_doc = AnalyzeTaskDocument.from_dict(doc)
        return TaskDocumentMapper.to_domain(task_doc)

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        self._collection.update_one({"_id": task_id}, {"$set": {"status": status.value}})

    def update_progress(self, task_id: str, stage: Stage, progress: StageProgress) -> None:
        progress_doc = TaskDocumentMapper.progress_to_document(progress)
        self._collection.update_one(
            {"_id": task_id},
            {"$set": {f"progress.{stage.value}": progress_doc.to_dict()}},
        )

    def complete(self, task_id: str, result: dict) -> None:
        self._collection.update_one(
            {"_id": task_id},
            {
                "$set": {
                    "status": TaskStatus.COMPLETED.value,
                    "result": result,
                    "completed_at": datetime.now(),
                }
            },
        )

    def fail(self, task_id: str, error: str) -> None:
        self._collection.update_one(
            {"_id": task_id},
            {
                "$set": {
                    "status": TaskStatus.FAILED.value,
                    "error": error,
                    "completed_at": datetime.now(),
                }
            },
        )

    def update_last_completed_phase(self, task_id: str, phase: Stage) -> None:
        self._collection.update_one(
            {"_id": task_id},
            {"$set": {"last_completed_phase": phase.value}},
        )
