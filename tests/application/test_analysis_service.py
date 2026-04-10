from unittest.mock import MagicMock

import pytest

from app.application.analysis_service import AnalysisService
from app.application.data_ingestor import DataIngestor
from app.domain.enums import TaskStatus
from app.domain.exceptions import ConflictError
from app.domain.models import AnalyzeTask
from app.domain.ports import IdGenerator, OutboxRepository, TaskRepository, TransactionManager
from app.domain.value_objects import IngestionResult, StageProgress


@pytest.fixture
def data_ingestor():
    return MagicMock(spec=DataIngestor)


@pytest.fixture
def id_generator():
    return MagicMock(spec=IdGenerator)


@pytest.fixture
def task_repo():
    return MagicMock(spec=TaskRepository)


@pytest.fixture
def outbox_repo():
    return MagicMock(spec=OutboxRepository)


@pytest.fixture
def tx_manager():
    mock = MagicMock(spec=TransactionManager)
    mock.execute.side_effect = lambda fn: fn()
    return mock


@pytest.fixture
def service(data_ingestor, id_generator, task_repo, outbox_repo, tx_manager):
    return AnalysisService(
        data_ingestor=data_ingestor,
        id_generator=id_generator,
        task_repo=task_repo,
        outbox_repo=outbox_repo,
        tx_manager=tx_manager,
    )


class TestAnalysisServiceSubmit:

    def test_정상_흐름_ingest_task_outbox_save(self, service, data_ingestor, id_generator, task_repo, outbox_repo):
        task_repo.find_by_statuses.return_value = None
        id_generator.generate.return_value = "outbox-id-1"
        data_ingestor.ingest.return_value = IngestionResult(
            task_id="task-1",
            selection_count=100,
            odd_count=80,
            label_count=60,
        )

        result = service.submit()

        assert result == "task-1"
        data_ingestor.ingest.assert_called_once()
        task_repo.save.assert_called_once()
        outbox_repo.save.assert_called_once()

        saved_task = task_repo.save.call_args[0][0]
        assert saved_task.task_id == "task-1"
        assert saved_task.status == TaskStatus.PENDING
        assert saved_task.selection_progress.total == 100
        assert saved_task.odd_tagging_progress.total == 80
        assert saved_task.auto_labeling_progress.total == 60

        saved_outbox = outbox_repo.save.call_args[0][0]
        assert saved_outbox.message_type == "ANALYZE"
        assert saved_outbox.payload == {"task_id": "task-1"}

    def test_중복_요청시_ConflictError(self, service, task_repo):
        existing = AnalyzeTask(
            task_id="existing-task",
            status=TaskStatus.PROCESSING,
            selection_progress=StageProgress(total=10),
            odd_tagging_progress=StageProgress(total=10),
            auto_labeling_progress=StageProgress(total=10),
        )
        task_repo.find_by_statuses.return_value = existing

        with pytest.raises(ConflictError, match="이미 진행 중인 작업"):
            service.submit()

    def test_중복_요청시_ingest_호출되지_않음(self, service, task_repo, data_ingestor):
        existing = AnalyzeTask(
            task_id="existing-task",
            status=TaskStatus.PENDING,
            selection_progress=StageProgress(total=10),
            odd_tagging_progress=StageProgress(total=10),
            auto_labeling_progress=StageProgress(total=10),
        )
        task_repo.find_by_statuses.return_value = existing

        with pytest.raises(ConflictError):
            service.submit()

        data_ingestor.ingest.assert_not_called()

    def test_트랜잭션_매니저_execute_호출됨(self, service, tx_manager, task_repo, data_ingestor, id_generator):
        task_repo.find_by_statuses.return_value = None
        id_generator.generate.return_value = "outbox-id-1"
        data_ingestor.ingest.return_value = IngestionResult(
            task_id="task-1", selection_count=10, odd_count=10, label_count=10,
        )

        service.submit()

        tx_manager.execute.assert_called_once()
