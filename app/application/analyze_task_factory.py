from app.domain.models import AnalyzeTask, AnalyzeTaskBundle, OutboxMessage
from app.domain.ports import IdGenerator
from app.domain.value_objects import IngestionResult


class AnalyzeTaskFactory:
    """AnalyzeTask + OutboxMessage를 생성하는 순수 팩토리

    저장소를 모르고, ID 생성 + 도메인 객체 조립만 담당한다.
    """

    def __init__(self, id_generator: IdGenerator) -> None:
        self._id_generator = id_generator

    def create(self, ingestion: IngestionResult) -> AnalyzeTaskBundle:
        """적재 결과를 받아 AnalyzeTask + OutboxMessage를 번들로 생성한다."""
        task = AnalyzeTask.create_new(
            task_id=ingestion.task_id,
            selection_count=ingestion.selection_count,
            odd_count=ingestion.odd_count,
            label_count=ingestion.label_count,
        )

        outbox = OutboxMessage.create_analyze_event(
            message_id=self._id_generator.generate(),
            task_id=ingestion.task_id,
        )

        return AnalyzeTaskBundle(task=task, outbox=outbox)
