import logging

from app.application.analyze_task_factory import AnalyzeTaskFactory
from app.domain.ports import TaskDispatcher, TaskRepository

logger = logging.getLogger(__name__)


class AnalysisService:
    """분석 요청 접수 서비스 (Command) — 팩토리로 Task 생성 + 저장 + 비동기 발행"""

    def __init__(
        self,
        task_factory: AnalyzeTaskFactory,
        task_repo: TaskRepository,
        task_dispatcher: TaskDispatcher,
    ) -> None:
        self._task_factory = task_factory
        self._task_repo = task_repo
        self._task_dispatcher = task_dispatcher

    def submit(self) -> str:
        """3개 파일을 MongoDB에 적재하고 비동기 정제 작업을 발행한다."""
        task = self._task_factory.create()

        self._task_repo.create(task)
        self._task_dispatcher.dispatch(task.task_id)

        logger.info("분석 접수: task_id=%s", task.task_id)
        return task.task_id
