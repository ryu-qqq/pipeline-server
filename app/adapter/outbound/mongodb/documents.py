from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawDataDocument:
    """MongoDB raw_data 컬렉션 도큐먼트"""

    task_id: str
    source: str
    data: dict
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "source": self.source,
            "data": self.data,
            "created_at": self.created_at,
        }


@dataclass
class StageProgressDocument:
    """단계별 진행률 도큐먼트"""

    total: int = 0
    processed: int = 0
    rejected: int = 0

    @property
    def percent(self) -> float:
        return round((self.processed + self.rejected) / self.total * 100, 1) if self.total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "processed": self.processed,
            "rejected": self.rejected,
            "percent": self.percent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StageProgressDocument":
        return cls(
            total=data.get("total", 0),
            processed=data.get("processed", 0),
            rejected=data.get("rejected", 0),
        )


@dataclass
class AnalyzeTaskDocument:
    """MongoDB analyze_tasks 컬렉션 도큐먼트"""

    task_id: str
    status: str
    selection_progress: StageProgressDocument = field(default_factory=StageProgressDocument)
    odd_tagging_progress: StageProgressDocument = field(default_factory=StageProgressDocument)
    auto_labeling_progress: StageProgressDocument = field(default_factory=StageProgressDocument)
    result: dict | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "_id": self.task_id,
            "status": self.status,
            "progress": {
                "selection": self.selection_progress.to_dict(),
                "odd_tagging": self.odd_tagging_progress.to_dict(),
                "auto_labeling": self.auto_labeling_progress.to_dict(),
            },
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, doc: dict) -> "AnalyzeTaskDocument":
        p = doc.get("progress", {})
        return cls(
            task_id=doc["_id"],
            status=doc["status"],
            selection_progress=StageProgressDocument.from_dict(p.get("selection", {})),
            odd_tagging_progress=StageProgressDocument.from_dict(p.get("odd_tagging", {})),
            auto_labeling_progress=StageProgressDocument.from_dict(p.get("auto_labeling", {})),
            result=doc.get("result"),
            error=doc.get("error"),
            created_at=doc.get("created_at"),
            completed_at=doc.get("completed_at"),
        )
