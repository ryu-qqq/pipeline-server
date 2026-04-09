from dataclasses import dataclass

from app.domain.exceptions import (
    InvalidFormatError,
    NegativeCountError,
    TemperatureConversionError,
)


@dataclass(frozen=True)
class VideoId:
    """영상 식별자"""

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int):
            raise InvalidFormatError(f"VideoId는 정수여야 합니다: {self.value}")
        if self.value <= 0:
            raise InvalidFormatError(f"VideoId는 양수여야 합니다: {self.value}")

    def __int__(self) -> int:
        return self.value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, VideoId):
            return self.value == other.value
        if isinstance(other, int):
            return self.value == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.value)


@dataclass(frozen=True)
class Temperature:
    """온도 (섭씨 기준)"""

    celsius: float

    def __post_init__(self) -> None:
        if self.celsius < -90 or self.celsius > 60:
            raise TemperatureConversionError(f"온도 범위 초과 (-90~60°C): {self.celsius}")

    @classmethod
    def from_celsius(cls, value: float) -> "Temperature":
        return cls(celsius=round(value, 2))

    @classmethod
    def from_fahrenheit(cls, value: float) -> "Temperature":
        celsius = (value - 32) * 5 / 9
        return cls(celsius=round(celsius, 2))


@dataclass(frozen=True)
class Confidence:
    """AI 모델 신뢰도 (0.0 ~ 1.0)"""

    value: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.value <= 1.0):
            raise InvalidFormatError(f"신뢰도는 0.0~1.0 범위여야 합니다: {self.value}")

    def is_high(self, threshold: float = 0.9) -> bool:
        return self.value >= threshold

    def is_low(self, threshold: float = 0.6) -> bool:
        return self.value < threshold


@dataclass(frozen=True)
class ObjectCount:
    """탐지된 객체 수 (0 이상 정수)"""

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int):
            raise InvalidFormatError(f"객체 수는 정수여야 합니다: {self.value}")
        if self.value < 0:
            raise NegativeCountError(f"객체 수는 음수일 수 없습니다: {self.value}")

    def is_empty(self) -> bool:
        return self.value == 0

    def __ge__(self, other: object) -> bool:
        if isinstance(other, ObjectCount):
            return self.value >= other.value
        if isinstance(other, int):
            return self.value >= other
        return NotImplemented

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True)
class WiperState:
    """와이퍼 상태"""

    active: bool
    level: int | None = None

    def __post_init__(self) -> None:
        if self.level is not None and not (0 <= self.level <= 3):
            raise InvalidFormatError(f"와이퍼 레벨은 0~3 범위여야 합니다: {self.level}")
        if not self.active and self.level is not None and self.level > 0:
            raise InvalidFormatError(f"와이퍼 비활성 상태에서 레벨이 {self.level}입니다")

    def is_raining_likely(self) -> bool:
        """와이퍼 상태로 비 올 가능성을 판단한다."""
        return self.active and self.level is not None and self.level >= 2


@dataclass(frozen=True)
class SourcePath:
    """영상 파일 경로"""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise InvalidFormatError("source_path는 비어있을 수 없습니다")
        if not self.value.endswith(".mp4"):
            raise InvalidFormatError(f"지원하지 않는 파일 형식: {self.value}")

    def is_raw(self) -> bool:
        """원본 데이터인지 판단한다."""
        return "/raw/" in self.value

    def is_processed(self) -> bool:
        """전처리된 데이터인지 판단한다."""
        return "/processed/" in self.value


@dataclass(frozen=True)
class StageProgress:
    """단계별 진행률"""

    total: int = 0
    processed: int = 0
    rejected: int = 0

    @property
    def percent(self) -> float:
        return round((self.processed + self.rejected) / self.total * 100, 1) if self.total > 0 else 0.0


@dataclass(frozen=True)
class StageResult:
    """단계별 처리 결과"""

    total: int
    loaded: int
    rejected: int
