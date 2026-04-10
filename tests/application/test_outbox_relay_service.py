from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch

import pytest

from app.application.outbox_relay_service import OutboxRelayService
from app.domain.enums import OutboxStatus
from app.domain.models import OutboxCriteria, OutboxMessage
from app.domain.ports import OutboxRepository, TaskDispatcher


@pytest.fixture
def outbox_repo():
    return MagicMock(spec=OutboxRepository)


@pytest.fixture
def task_dispatcher():
    return MagicMock(spec=TaskDispatcher)


@pytest.fixture
def service(outbox_repo, task_dispatcher):
    return OutboxRelayService(outbox_repo, task_dispatcher, fetch_limit=10)


def _make_message(message_id="msg-1", task_id="task-1", status=OutboxStatus.PENDING, retry_count=0) -> OutboxMessage:
    return OutboxMessage(
        message_id=message_id,
        message_type="ANALYZE",
        payload={"task_id": task_id},
        status=status,
        retry_count=retry_count,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


class TestOutboxRelayService:

    def test_relay_정상흐름_순서검증(self, service, outbox_repo, task_dispatcher):
        """PENDING 조회 → mark_processing → save → dispatch → mark_published → save"""
        msg = _make_message()
        outbox_repo.find_by.return_value = [msg]

        published = service.relay()

        assert published == 1
        task_dispatcher.dispatch.assert_called_once_with("task-1")
        assert outbox_repo.save.call_count == 2

        first_save = outbox_repo.save.call_args_list[0][0][0]
        assert first_save.status == OutboxStatus.PROCESSING

        second_save = outbox_repo.save.call_args_list[1][0][0]
        assert second_save.status == OutboxStatus.PUBLISHED

    def test_relay_여러건_처리(self, service, outbox_repo, task_dispatcher):
        msg1 = _make_message("msg-1", "task-1")
        msg2 = _make_message("msg-2", "task-2")
        outbox_repo.find_by.return_value = [msg1, msg2]

        published = service.relay()

        assert published == 2
        assert task_dispatcher.dispatch.call_count == 2

    def test_relay_PENDING_없으면_0_반환(self, service, outbox_repo):
        outbox_repo.find_by.return_value = []

        assert service.relay() == 0

    def test_relay_발행_실패시_processing_상태_유지(self, service, outbox_repo, task_dispatcher):
        msg = _make_message()
        outbox_repo.find_by.return_value = [msg]
        task_dispatcher.dispatch.side_effect = RuntimeError("발행 실패")

        published = service.relay()

        assert published == 0
        # mark_processing → save만 호출 (mark_published는 호출 안 됨)
        assert outbox_repo.save.call_count == 1
        saved = outbox_repo.save.call_args_list[0][0][0]
        assert saved.status == OutboxStatus.PROCESSING

    def test_relay_부분_실패시_성공건수만_반환(self, service, outbox_repo, task_dispatcher):
        msg1 = _make_message("msg-1", "task-1")
        msg2 = _make_message("msg-2", "task-2")
        outbox_repo.find_by.return_value = [msg1, msg2]
        task_dispatcher.dispatch.side_effect = [None, RuntimeError("실패")]

        published = service.relay()

        assert published == 1


class TestOutboxRecoverZombies:

    def test_재시도_가능하면_back_to_pending(self, service, outbox_repo):
        zombie = _make_message(status=OutboxStatus.PROCESSING, retry_count=0)
        outbox_repo.find_by.return_value = [zombie]

        recovered = service.recover_zombies(threshold_minutes=5)

        assert recovered == 1
        saved = outbox_repo.save.call_args[0][0]
        assert saved.status == OutboxStatus.PENDING
        assert saved.retry_count == 1

    def test_재시도_초과시_mark_failed(self, service, outbox_repo):
        zombie = _make_message(status=OutboxStatus.PROCESSING, retry_count=3)
        outbox_repo.find_by.return_value = [zombie]

        recovered = service.recover_zombies()

        assert recovered == 1
        saved = outbox_repo.save.call_args[0][0]
        assert saved.status == OutboxStatus.FAILED
        assert saved.retry_count == 4

    def test_좀비_없으면_0_반환(self, service, outbox_repo):
        outbox_repo.find_by.return_value = []

        assert service.recover_zombies() == 0

    def test_여러_좀비_개별_처리(self, service, outbox_repo):
        z1 = _make_message("z1", retry_count=0, status=OutboxStatus.PROCESSING)
        z2 = _make_message("z2", retry_count=3, status=OutboxStatus.PROCESSING)
        outbox_repo.find_by.return_value = [z1, z2]

        recovered = service.recover_zombies()

        assert recovered == 2
        saves = [c[0][0] for c in outbox_repo.save.call_args_list]
        assert saves[0].status == OutboxStatus.PENDING
        assert saves[1].status == OutboxStatus.FAILED
