from app.domain.ports import TaskDispatcher


class CeleryTaskDispatcher(TaskDispatcher):
    """Celery 기반 비동기 작업 발행 구현체"""

    def dispatch(self, task_id: str) -> None:
        from app.adapter.inbound.worker.pipeline_task import process_analysis

        process_analysis.delay(task_id)
