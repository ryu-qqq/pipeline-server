from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.exceptions import UnknownSchemaError
from app.domain.models import Selection
from app.domain.value_objects import SourcePath, Temperature, VideoId, WiperState


class SelectionParser(ABC):
    """Selection 파싱 전략 인터페이스"""

    @abstractmethod
    def parse(self, raw: dict) -> Selection: ...


class V1SelectionParser(SelectionParser):
    """v1 (flat) 스키마 파서 — 섭씨 원본, 와이퍼 레벨 없음"""

    def parse(self, raw: dict) -> Selection:
        return Selection(
            id=VideoId(raw["id"]),
            recorded_at=_parse_datetime(raw["recordedAt"]),
            temperature=Temperature.from_celsius(float(raw["temperature"])),
            wiper=WiperState(active=bool(raw["isWiperOn"])),
            headlights_on=bool(raw["headlightsOn"]),
            source_path=SourcePath(raw["sourcePath"]),
        )


class V2SelectionParser(SelectionParser):
    """v2 (sensor) 스키마 파서 — 화씨→섭씨 변환, 와이퍼 레벨 있음"""

    def parse(self, raw: dict) -> Selection:
        sensor = raw["sensor"]
        temp_value = sensor["temperature"]["value"]
        temp_unit = sensor["temperature"].get("unit", "F")

        if temp_unit == "F":
            temperature = Temperature.from_fahrenheit(temp_value)
        elif temp_unit == "C":
            temperature = Temperature.from_celsius(float(temp_value))
        else:
            raise ValueError(f"알 수 없는 온도 단위: {temp_unit}")

        return Selection(
            id=VideoId(raw["id"]),
            recorded_at=_parse_datetime(raw["recordedAt"]),
            temperature=temperature,
            wiper=WiperState(
                active=bool(sensor["wiper"]["isActive"]),
                level=int(sensor["wiper"]["level"]),
            ),
            headlights_on=bool(sensor["headlights"]),
            source_path=SourcePath(raw["sourcePath"]),
        )


def detect_parser(raw: dict) -> SelectionParser:
    """스키마를 감지하여 적절한 파서를 반환한다."""
    if "sensor" in raw:
        return V2SelectionParser()
    if "temperature" in raw:
        return V1SelectionParser()
    raise UnknownSchemaError(f"알 수 없는 스키마: {list(raw.keys())}")


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
