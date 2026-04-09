import uuid

from app.domain.ports import IdGenerator


class UUIDv4Generator(IdGenerator):
    """UUIDv4 기반 고유 식별자 생성기"""

    def generate(self) -> str:
        return str(uuid.uuid4())
