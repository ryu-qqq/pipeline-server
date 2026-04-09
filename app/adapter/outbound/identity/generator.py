from uuid_utils import uuid7

from app.domain.ports import IdGenerator


class UUIDv7Generator(IdGenerator):
    """UUIDv7 기반 고유 식별자 생성기 — 타임스탬프 순서 보장"""

    def generate(self) -> str:
        return str(uuid7())
