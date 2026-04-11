import dataclasses

from app.adapter.outbound.mongodb.documents import (
    AnalyzeTaskDocument,
    OutboxDocument,
    StageProgressDocument,
)
from app.domain.enums import OutboxStatus, Stage, TaskStatus
from app.domain.models import AnalysisResult, AnalyzeTask, OutboxMessage
from app.domain.value_objects import StageProgress, StageResult


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
            last_completed_phase=domain.last_completed_phase.value if domain.last_completed_phase else None,
            result=dataclasses.asdict(domain.result) if domain.result else None,
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
            last_completed_phase=Stage(doc.last_completed_phase) if doc.last_completed_phase else None,
            result=TaskDocumentMapper._to_analysis_result(doc.result) if doc.result else None,
            error=doc.error,
            created_at=doc.created_at,
            completed_at=doc.completed_at,
        )

    @staticmethod
    def _to_analysis_result(data: dict) -> AnalysisResult:
        def _to_stage_result(d: dict) -> StageResult:
            return StageResult(total=d["total"], loaded=d["loaded"], rejected=d["rejected"])

        return AnalysisResult(
            selection=_to_stage_result(data["selection"]),
            odd_tagging=_to_stage_result(data["odd_tagging"]),
            auto_labeling=_to_stage_result(data["auto_labeling"]),
            fully_linked=data["fully_linked"],
            partial=data["partial"],
        )

    @staticmethod
    def progress_to_document(domain: StageProgress) -> StageProgressDocument:
        return StageProgressDocument(
            total=domain.total,
            processed=domain.processed,
            rejected=domain.rejected,
        )


class OutboxDocumentMapper:
    """도메인 OutboxMessage ↔ MongoDB OutboxDocument 변환"""

    @staticmethod
    def to_document(domain: OutboxMessage) -> OutboxDocument:
        return OutboxDocument(
            message_id=domain.message_id,
            message_type=domain.message_type,
            payload=domain.payload,
            status=domain.status.value,
            retry_count=domain.retry_count,
            max_retries=domain.max_retries,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
        )

    @staticmethod
    def to_domain(doc: OutboxDocument) -> OutboxMessage:
        return OutboxMessage(
            message_id=doc.message_id,
            message_type=doc.message_type,
            payload=doc.payload,
            status=OutboxStatus(doc.status),
            retry_count=doc.retry_count,
            max_retries=doc.max_retries,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
