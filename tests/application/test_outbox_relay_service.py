from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.application.outbox_relay_service import OutboxRelayService
from app.domain.enums import OutboxStatus
from app.domain.models import OutboxMessage
from app.domain.ports import OutboxRepository, TaskDispatcher


@pytest.fixture
def outbox_repo():
    repo = MagicMock(spec=OutboxRepository)
    repo.save_if_status.return_value = True  # 기본: 낙관적 잠금 성공
    return repo


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
        """PENDING 조회 → mark_processing → save → dispatch → mark_published → save_if_status"""
        msg = _make_message()
        outbox_repo.find_by.return_value = [msg]

        published = service.relay()

        assert published == 1
        task_dispatcher.dispatch.assert_called_once_with("task-1")

        # mark_processing → save (무조건 저장)
        first_save = outbox_repo.save.call_args_list[0][0][0]
        assert first_save.status == OutboxStatus.PROCESSING

        # mark_published → save_if_status (낙관적 잠금)
        published_save = outbox_repo.save_if_status.call_args_list[0][0][0]
        assert published_save.status == OutboxStatus.PUBLISHED
        expected_status = outbox_repo.save_if_status.call_args_list[0][0][1]
        assert expected_status == OutboxStatus.PROCESSING

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
        # mark_processing → save만 호출
        assert outbox_repo.save.call_count == 1
        saved = outbox_repo.save.call_args_list[0][0][0]
        assert saved.status == OutboxStatus.PROCESSING
        # save_if_status는 호출되지 않음 (예외로 건너뜀)
        outbox_repo.save_if_status.assert_not_called()

    def test_relay_부분_실패시_성공건수만_반환(self, service, outbox_repo, task_dispatcher):
        msg1 = _make_message("msg-1", "task-1")
        msg2 = _make_message("msg-2", "task-2")
        outbox_repo.find_by.return_value = [msg1, msg2]
        task_dispatcher.dispatch.side_effect = [None, RuntimeError("실패")]

        published = service.relay()

        assert published == 1

    def test_relay_낙관적_잠금_실패시_published_미증가(self, service, outbox_repo, task_dispatcher):
        """save_if_status가 False를 반환하면 (이미 다른 프로세스가 처리) published 미증가"""
        msg = _make_message()
        outbox_repo.find_by.return_value = [msg]
        outbox_repo.save_if_status.return_value = False

        published = service.relay()

        assert published == 0
        task_dispatcher.dispatch.assert_called_once()  # dispatch는 호출됨


class TestOutboxRecoverZombies:

    def test_재시도_가능하면_back_to_pending(self, service, outbox_repo):
        zombie = _make_message(status=OutboxStatus.PROCESSING, retry_count=0)
        outbox_repo.find_by.return_value = [zombie]

        recovered = service.recover_zombies(threshold_minutes=5)

        assert recovered == 1
        saved = outbox_repo.save_if_status.call_args[0][0]
        assert saved.status == OutboxStatus.PENDING
        assert saved.retry_count == 1
        # expected_status = PROCESSING
        expected = outbox_repo.save_if_status.call_args[0][1]
        assert expected == OutboxStatus.PROCESSING

    def test_재시도_초과시_mark_failed(self, service, outbox_repo):
        zombie = _make_message(status=OutboxStatus.PROCESSING, retry_count=3)
        outbox_repo.find_by.return_value = [zombie]

        recovered = service.recover_zombies()

        assert recovered == 1
        saved = outbox_repo.save_if_status.call_args[0][0]
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
        saves = [c[0][0] for c in outbox_repo.save_if_status.call_args_list]
        assert saves[0].status == OutboxStatus.PENDING
        assert saves[1].status == OutboxStatus.FAILED

    def test_낙관적_잠금_실패시_recovered_미증가(self, service, outbox_repo):
        """이미 relay()가 PUBLISHED로 전환한 메시지는 recover가 덮어쓰지 않는다"""
        zombie = _make_message(status=OutboxStatus.PROCESSING, retry_count=0)
        outbox_repo.find_by.return_value = [zombie]
        outbox_repo.save_if_status.return_value = False  # 이미 상태 변경됨

        recovered = service.recover_zombies()

        assert recovered == 0

    def test_개별_save_실패시_나머지_계속_처리(self, service, outbox_repo):
        """한 건의 save가 실패해도 나머지 좀비는 계속 처리된다"""
        z1 = _make_message("z1", retry_count=0, status=OutboxStatus.PROCESSING)
        z2 = _make_message("z2", retry_count=0, status=OutboxStatus.PROCESSING)
        outbox_repo.find_by.return_value = [z1, z2]
        outbox_repo.save_if_status.side_effect = [RuntimeError("DB 에러"), True]

        recovered = service.recover_zombies()

        assert recovered == 1  # z1 실패, z2 성공
