import functools
from collections.abc import Callable


def transactional(method: Callable) -> Callable:
    """트랜잭션 데코레이터 (= Spring @Transactional)

    서비스 메서드에 붙이면 메서드 내부의 모든 저장소 작업이
    TransactionManager를 통해 하나의 트랜잭션으로 묶인다.

    사용법:
        class AnalysisService:
            def __init__(self, ..., tx_manager: TransactionManager):
                self._tx_manager = tx_manager

            @transactional
            def submit(self) -> str:
                ...

    주의:
        - 데코레이터를 붙인 메서드의 클래스에 self._tx_manager가 있어야 한다.
        - 실제 트랜잭션 범위는 주입된 TransactionManager 구현체에 따라 결정된다.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        result = None

        def _run() -> None:
            nonlocal result
            result = method(self, *args, **kwargs)

        self._tx_manager.execute(_run)
        return result

    return wrapper
