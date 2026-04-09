from datetime import datetime

from pymongo.database import Database

from app.domain.ports import AnalyzeTask, RawDataRepository, StageProgress, TaskRepository

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
        """청크 단위 벌크 insert"""
        total = 0
        now = datetime.now()
        for i in range(0, len(items), BULK_INSERT_SIZE):
            chunk = items[i : i + BULK_INSERT_SIZE]
            docs = [
                {
                    "task_id": task_id,
                    "source": source,
                    "data": item,
                    "created_at": now,
                }
                for item in chunk
            ]
            self._collection.insert_many(docs)
            total += len(chunk)
        return total


class MongoTaskRepository(TaskRepository):
    """MongoDB 분석 작업 상태 저장소 구현체"""

    def __init__(self, db: Database) -> None:
        self._collection = db.analyze_tasks

    def create(self, task: AnalyzeTask) -> None:
        self._collection.insert_one(
            {
                "_id": task.task_id,
                "status": task.status,
                "progress": {
                    "selection": self._progress_to_dict(task.selection_progress),
                    "odd_tagging": self._progress_to_dict(task.odd_tagging_progress),
                    "auto_labeling": self._progress_to_dict(task.auto_labeling_progress),
                },
                "result": task.result,
                "error": task.error,
                "created_at": task.created_at or datetime.now(),
                "completed_at": task.completed_at,
            }
        )

    def find_by_id(self, task_id: str) -> AnalyzeTask | None:
        doc = self._collection.find_one({"_id": task_id})
        if not doc:
            return None
        return self._to_domain(doc)

    def update_status(self, task_id: str, status: str) -> None:
        self._collection.update_one({"_id": task_id}, {"$set": {"status": status}})

    def update_progress(self, task_id: str, stage: str, progress: StageProgress) -> None:
        self._collection.update_one(
            {"_id": task_id},
            {"$set": {f"progress.{stage}": self._progress_to_dict(progress)}},
        )

    def complete(self, task_id: str, result: dict) -> None:
        self._collection.update_one(
            {"_id": task_id},
            {
                "$set": {
                    "status": "completed",
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
                    "status": "failed",
                    "error": error,
                    "completed_at": datetime.now(),
                }
            },
        )

    @staticmethod
    def _progress_to_dict(progress: StageProgress) -> dict:
        return {
            "total": progress.total,
            "processed": progress.processed,
            "rejected": progress.rejected,
            "percent": progress.percent,
        }

    @staticmethod
    def _to_domain(doc: dict) -> AnalyzeTask:
        p = doc.get("progress", {})
        return AnalyzeTask(
            task_id=doc["_id"],
            status=doc["status"],
            selection_progress=StageProgress(**{k: v for k, v in p.get("selection", {}).items() if k != "percent"}),
            odd_tagging_progress=StageProgress(**{k: v for k, v in p.get("odd_tagging", {}).items() if k != "percent"}),
            auto_labeling_progress=StageProgress(
                **{k: v for k, v in p.get("auto_labeling", {}).items() if k != "percent"}
            ),
            result=doc.get("result"),
            error=doc.get("error"),
            created_at=doc.get("created_at"),
            completed_at=doc.get("completed_at"),
        )
