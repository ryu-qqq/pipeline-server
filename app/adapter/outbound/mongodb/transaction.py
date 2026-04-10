"""MongoDB 트랜잭션 관리 — contextvars 기반 세션 전파.

MongoTransactionManager가 트랜잭션을 시작하면 contextvars에 세션을 저장하고,
각 Repository는 get_current_session()으로 현재 세션을 가져와 operation에 전달한다.
트랜잭션 밖에서 호출되면 None을 반환하여 세션 없이 동작한다.
"""

import contextvars
from collections.abc import Callable

from pymongo import MongoClient
from pymongo.client_session import ClientSession

from app.domain.ports import TransactionManager

_current_session: contextvars.ContextVar[ClientSession | None] = contextvars.ContextVar(
    "_current_session",
    default=None,
)


def get_current_session() -> ClientSession | None:
    """현재 트랜잭션 세션을 반환한다. 트랜잭션 밖이면 None."""
    return _current_session.get()


class MongoTransactionManager(TransactionManager):
    """MongoDB Replica Set 트랜잭션 관리 구현체."""

    def __init__(self, client: MongoClient) -> None:
        self._client = client

    def execute(self, fn: Callable[[], None]) -> None:
        """fn 내부의 모든 MongoDB 작업을 하나의 트랜잭션으로 실행한다."""
        with self._client.start_session() as session, session.start_transaction():
            _current_session.set(session)
            try:
                fn()
            finally:
                _current_session.set(None)
