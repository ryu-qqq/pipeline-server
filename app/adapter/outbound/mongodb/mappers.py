from app.adapter.outbound.mongodb.documents import (
    AnalyzeTaskDocument,
    StageProgressDocument,
)
from app.domain.enums import TaskStatus
from app.domain.ports import AnalyzeTask, StageProgress


class TaskDocumentMapper:
    """도메인 AnalyzeTask ↔ MongoDB AnalyzeTaskDocument 변환"""

    @staticmethod
    def to_document(domain: AnalyzeTask) -> AnalyzeTaskDocument:
        return AnalyzeTaskDocument(
            task_id=domain.task_id,
            status=domain.status.value,
            selection_progress=StageProgressDocument(
                total=domain.selection_progress.total,
                processed=domain.selection_progress.processed,
                rejected=domain.selection_progress.rejected,
            ),
            odd_tagging_progress=StageProgressDocument(
                total=domain.odd_tagging_progress.total,
                processed=domain.odd_tagging_progress.processed,
                rejected=domain.odd_tagging_progress.rejected,
            ),
            auto_labeling_progress=StageProgressDocument(
                total=domain.auto_labeling_progress.total,
                processed=domain.auto_labeling_progress.processed,
                rejected=domain.auto_labeling_progress.rejected,
            ),
            result=domain.result,
            error=domain.error,
            created_at=domain.created_at,
            completed_at=domain.completed_at,
        )

    @staticmethod
    def to_domain(doc: AnalyzeTaskDocument) -> AnalyzeTask:
        return AnalyzeTask(
            task_id=doc.task_id,
            status=TaskStatus(doc.status),
            selection_progress=StageProgress(
                total=doc.selection_progress.total,
                processed=doc.selection_progress.processed,
                rejected=doc.selection_progress.rejected,
            ),
            odd_tagging_progress=StageProgress(
                total=doc.odd_tagging_progress.total,
                processed=doc.odd_tagging_progress.processed,
                rejected=doc.odd_tagging_progress.rejected,
            ),
            auto_labeling_progress=StageProgress(
                total=doc.auto_labeling_progress.total,
                processed=doc.auto_labeling_progress.processed,
                rejected=doc.auto_labeling_progress.rejected,
            ),
            result=doc.result,
            error=doc.error,
            created_at=doc.created_at,
            completed_at=doc.completed_at,
        )

    @staticmethod
    def progress_to_document(domain: StageProgress) -> StageProgressDocument:
        return StageProgressDocument(
            total=domain.total,
            processed=domain.processed,
            rejected=domain.rejected,
        )
