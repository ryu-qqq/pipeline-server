from datetime import datetime

from app.domain.enums import RejectionReason, Stage
from app.domain.exceptions import DomainError, UnknownSchemaError
from app.domain.models import Rejection, Selection
from app.domain.value_objects import SourcePath, Temperature, VideoId, WiperState


class SelectionRefiner:
    """Selection 원본 데이터를 도메인 모델로 정제한다.

    모든 필드를 검증하고, 에러가 여러 개면 에러별로 각각 Rejection을 생성한다.
    V1/V2 스키마를 자동 감지하여 적절한 파싱 전략을 적용한다.
    """

    def refine_single(self, task_id: str, row: dict) -> Selection | list[Rejection]:
        source_id = str(row.get("id", "?"))
        now = datetime.now()

        schema = self._detect_schema(row, source_id, task_id, now)
        if isinstance(schema, Rejection):
            return [schema]

        if schema == "v2":
            return self._refine_v2(task_id, row, source_id, now)
        return self._refine_v1(task_id, row, source_id, now)

    def _refine_v1(self, task_id: str, row: dict, source_id: str, now: datetime) -> Selection | list[Rejection]:
        rejections: list[Rejection] = []

        video_id = self._parse_video_id(row, "id", source_id, task_id, rejections, now)
        recorded_at = self._parse_datetime(row, "recordedAt", source_id, task_id, rejections, now)
        temperature = self._parse_temperature_celsius(row, "temperature", source_id, task_id, rejections, now)
        wiper = self._parse_v1_wiper(row, source_id, task_id, rejections, now)
        headlights_on = self._parse_bool(row, "headlightsOn", source_id, task_id, rejections, now)
        source_path = self._parse_source_path(row, "sourcePath", source_id, task_id, rejections, now)

        if rejections:
            return rejections

        return Selection(
            id=video_id, task_id=task_id, recorded_at=recorded_at,
            temperature=temperature, wiper=wiper,
            headlights_on=headlights_on, source_path=source_path,
        )

    def _refine_v2(self, task_id: str, row: dict, source_id: str, now: datetime) -> Selection | list[Rejection]:
        rejections: list[Rejection] = []

        video_id = self._parse_video_id(row, "id", source_id, task_id, rejections, now)
        recorded_at = self._parse_datetime(row, "recordedAt", source_id, task_id, rejections, now)
        source_path = self._parse_source_path(row, "sourcePath", source_id, task_id, rejections, now)

        sensor = row.get("sensor")
        if not isinstance(sensor, dict):
            rejections.append(self._reject(task_id, source_id, "sensor", RejectionReason.INVALID_FORMAT, "sensor 필드가 유효하지 않음", now))
            return rejections

        temperature = self._parse_v2_temperature(sensor, source_id, task_id, rejections, now)
        wiper = self._parse_v2_wiper(sensor, source_id, task_id, rejections, now)
        headlights_on = self._parse_bool(sensor, "headlights", source_id, task_id, rejections, now)

        if rejections:
            return rejections

        return Selection(
            id=video_id, task_id=task_id, recorded_at=recorded_at,
            temperature=temperature, wiper=wiper,
            headlights_on=headlights_on, source_path=source_path,
        )

    @staticmethod
    def _detect_schema(row: dict, source_id: str, task_id: str, now: datetime) -> str | Rejection:
        if "sensor" in row:
            return "v2"
        if "temperature" in row:
            return "v1"
        return Rejection(
            task_id=task_id, stage=Stage.SELECTION, reason=RejectionReason.UNKNOWN_SCHEMA,
            source_id=source_id, field="schema", detail=f"알 수 없는 스키마: {list(row.keys())}", created_at=now,
        )

    # === 공통 파서 ===

    def _parse_video_id(self, row: dict, field: str, source_id: str, task_id: str, rejections: list, now: datetime) -> VideoId | None:
        try:
            return VideoId(row[field])
        except (DomainError, ValueError, KeyError, TypeError) as e:
            rejections.append(self._reject(task_id, source_id, field, RejectionReason.INVALID_FORMAT, f"{field} 파싱 불가: {e}", now))
            return None

    def _parse_datetime(self, row: dict, field: str, source_id: str, task_id: str, rejections: list, now: datetime) -> datetime | None:
        try:
            return datetime.fromisoformat(row[field])
        except (DomainError, ValueError, KeyError, TypeError) as e:
            rejections.append(self._reject(task_id, source_id, field, RejectionReason.INVALID_FORMAT, f"{field} 파싱 불가: {e}", now))
            return None

    def _parse_bool(self, row: dict, field: str, source_id: str, task_id: str, rejections: list, now: datetime) -> bool | None:
        try:
            return bool(row[field])
        except KeyError:
            rejections.append(self._reject(task_id, source_id, field, RejectionReason.MISSING_REQUIRED_FIELD, f"{field} 누락", now))
            return None

    def _parse_source_path(self, row: dict, field: str, source_id: str, task_id: str, rejections: list, now: datetime) -> SourcePath | None:
        try:
            return SourcePath(row[field])
        except (DomainError, ValueError, KeyError, TypeError) as e:
            rejections.append(self._reject(task_id, source_id, field, RejectionReason.INVALID_FORMAT, f"{field} 파싱 불가: {e}", now))
            return None

    def _parse_temperature_celsius(self, row: dict, field: str, source_id: str, task_id: str, rejections: list, now: datetime) -> Temperature | None:
        try:
            return Temperature.from_celsius(float(row[field]))
        except (DomainError, ValueError, KeyError, TypeError) as e:
            rejections.append(self._reject(task_id, source_id, field, RejectionReason.INVALID_FORMAT, f"{field} 파싱 불가: {e}", now))
            return None

    def _parse_v1_wiper(self, row: dict, source_id: str, task_id: str, rejections: list, now: datetime) -> WiperState | None:
        try:
            return WiperState(active=bool(row["isWiperOn"]))
        except KeyError:
            rejections.append(self._reject(task_id, source_id, "isWiperOn", RejectionReason.MISSING_REQUIRED_FIELD, "isWiperOn 누락", now))
            return None

    def _parse_v2_temperature(self, sensor: dict, source_id: str, task_id: str, rejections: list, now: datetime) -> Temperature | None:
        try:
            temp_data = sensor["temperature"]
            value = temp_data["value"]
            unit = temp_data.get("unit", "F")
            if unit == "F":
                return Temperature.from_fahrenheit(value)
            elif unit == "C":
                return Temperature.from_celsius(float(value))
            else:
                rejections.append(self._reject(task_id, source_id, "sensor.temperature.unit", RejectionReason.INVALID_FORMAT, f"알 수 없는 온도 단위: {unit}", now))
                return None
        except (DomainError, ValueError, KeyError, TypeError) as e:
            rejections.append(self._reject(task_id, source_id, "sensor.temperature", RejectionReason.INVALID_FORMAT, f"temperature 파싱 불가: {e}", now))
            return None

    def _parse_v2_wiper(self, sensor: dict, source_id: str, task_id: str, rejections: list, now: datetime) -> WiperState | None:
        try:
            wiper_data = sensor["wiper"]
            return WiperState(active=bool(wiper_data["isActive"]), level=int(wiper_data["level"]))
        except (DomainError, ValueError, KeyError, TypeError) as e:
            rejections.append(self._reject(task_id, source_id, "sensor.wiper", RejectionReason.INVALID_FORMAT, f"wiper 파싱 불가: {e}", now))
            return None

    @staticmethod
    def _reject(task_id: str, source_id: str, field: str, reason: RejectionReason, detail: str, now: datetime) -> Rejection:
        return Rejection(
            task_id=task_id, stage=Stage.SELECTION, reason=reason,
            source_id=source_id, field=field, detail=detail, created_at=now,
        )
