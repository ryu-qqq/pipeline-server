from app.domain.exceptions import DataNotFoundError
from app.domain.models import AnalyzeTask
from app.domain.ports import TaskRepository


class TaskService:
    """분석 작업 상태 조회 서비스 (Query)"""

    def __init__(self, task_repo: TaskRepository) -> None:
        self._task_repo = task_repo

    def get_task(self, task_id: str) -> AnalyzeTask:
        task = self._task_repo.find_by_id(task_id)
        if task is None:
            raise DataNotFoundError(f"작업을 찾을 수 없습니다: {task_id}")
        return task
