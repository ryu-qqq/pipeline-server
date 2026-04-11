from unittest.mock import MagicMock

import pytest

from app.application.data_read_service import DataReadService
from app.application.rejection_read_service import RejectionReadService
from app.application.task_read_service import TaskReadService
from app.domain.enums import TaskStatus
from app.domain.exceptions import DataNotFoundError
from app.domain.models import AnalyzeTask, DataSearchCriteria, RejectionCriteria
from app.domain.ports import DataSearchRepository, RejectionRepository, TaskRepository
from app.domain.value_objects import StageProgress

# === TaskReadService ===


class TestTaskReadService:

    def test_get_task_정상_반환(self):
        """find_by_id가 작업을 찾으면 그대로 반환한다"""
        # Arrange
        mock_repo = MagicMock(spec=TaskRepository)
        task = AnalyzeTask(
            task_id="task-001",
            status=TaskStatus.PENDING,
            selection_progress=StageProgress(total=10),
            odd_tagging_progress=StageProgress(total=5),
            auto_labeling_progress=StageProgress(total=3),
        )
        mock_repo.find_by_id.return_value = task
        service = TaskReadService(task_repo=mock_repo)

        # Act
        result = service.get_task("task-001")

        # Assert
        assert result is task
        assert result.task_id == "task-001"
        mock_repo.find_by_id.assert_called_once_with("task-001")

    def test_get_task_미존재시_DataNotFoundError(self):
        """find_by_id가 None을 반환하면 DataNotFoundError가 발생한다"""
        # Arrange
        mock_repo = MagicMock(spec=TaskRepository)
        mock_repo.find_by_id.return_value = None
        service = TaskReadService(task_repo=mock_repo)

        # Act & Assert
        with pytest.raises(DataNotFoundError, match="작업을 찾을 수 없습니다"):
            service.get_task("nonexistent-task")

        mock_repo.find_by_id.assert_called_once_with("nonexistent-task")


# === DataReadService ===


class TestDataReadService:

    def test_search_정상_위임(self):
        """search_repo.search()에 위임하고 결과를 그대로 반환한다"""
        # Arrange
        mock_repo = MagicMock(spec=DataSearchRepository)
        expected_results = ([MagicMock()], 1)
        mock_repo.search.return_value = expected_results
        service = DataReadService(search_repo=mock_repo)
        criteria = DataSearchCriteria(task_id="task-001")

        # Act
        result = service.search(criteria)

        # Assert
        assert result is expected_results
        mock_repo.search.assert_called_once_with(criteria)

    def test_search_빈_결과(self):
        """검색 결과가 없으면 빈 리스트와 0을 반환한다"""
        # Arrange
        mock_repo = MagicMock(spec=DataSearchRepository)
        mock_repo.search.return_value = ([], 0)
        service = DataReadService(search_repo=mock_repo)
        criteria = DataSearchCriteria()

        # Act
        results, total = service.search(criteria)

        # Assert
        assert results == []
        assert total == 0


# === RejectionReadService ===


class TestRejectionReadService:

    def test_search_정상_위임(self):
        """rejection_repo.search()에 위임하고 결과를 그대로 반환한다"""
        # Arrange
        mock_repo = MagicMock(spec=RejectionRepository)
        expected_results = ([MagicMock()], 5)
        mock_repo.search.return_value = expected_results
        service = RejectionReadService(rejection_repo=mock_repo)
        criteria = RejectionCriteria(task_id="task-001")

        # Act
        result = service.search(criteria)

        # Assert
        assert result is expected_results
        mock_repo.search.assert_called_once_with(criteria)

    def test_search_빈_결과(self):
        """거부 데이터가 없으면 빈 리스트와 0을 반환한다"""
        # Arrange
        mock_repo = MagicMock(spec=RejectionRepository)
        mock_repo.search.return_value = ([], 0)
        service = RejectionReadService(rejection_repo=mock_repo)
        criteria = RejectionCriteria()

        # Act
        results, total = service.search(criteria)

        # Assert
        assert results == []
        assert total == 0
