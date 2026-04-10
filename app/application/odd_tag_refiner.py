from datetime import datetime

from app.domain.enums import RejectionReason, RoadSurface, Stage, TimeOfDay, Weather
from app.domain.models import OddTag, Rejection
from app.domain.value_objects import VideoId


class OddTagRefiner:
    """ODD 태깅 원본 데이터를 도메인 모델로 정제한다.

    모든 필드를 검증하고, 에러가 여러 개면 에러별로 각각 Rejection을 생성한다.
    중복 탐지는 MySQL UNIQUE 제약에 위임한다.
    """

    def refine_single(self, task_id: str, row: dict) -> OddTag | list[Rejection]:
        rejections: list[Rejection] = []
        source_id = str(row.get("id", "?"))
        now = datetime.now()

        odd_id = self._parse_int(row, "id", source_id, task_id, rejections, now)
        video_id = self._parse_video_id(row, source_id, task_id, rejections, now)
        weather = self._parse_enum(row, "weather", Weather, source_id, task_id, rejections, now)
        time_of_day = self._parse_enum(row, "time_of_day", TimeOfDay, source_id, task_id, rejections, now)
        road_surface = self._parse_enum(row, "road_surface", RoadSurface, source_id, task_id, rejections, now)

        if rejections:
            return rejections

        return OddTag(
            id=odd_id, task_id=task_id, video_id=video_id,
            weather=weather, time_of_day=time_of_day, road_surface=road_surface,
        )

    def _parse_int(self, row: dict, field: str, source_id: str, task_id: str, rejections: list, now: datetime) -> int | None:
        try:
            return int(row[field])
        except (ValueError, KeyError, TypeError):
            rejections.append(self._reject(task_id, source_id, field, RejectionReason.INVALID_FORMAT, f"{field} 파싱 불가: {row.get(field, '누락')}", now))
            return None

    def _parse_video_id(self, row: dict, source_id: str, task_id: str, rejections: list, now: datetime) -> VideoId | None:
        try:
            raw = str(row["video_id"]).lstrip("0") or "0"
            return VideoId(int(raw))
        except (ValueError, KeyError, TypeError):
            rejections.append(self._reject(task_id, source_id, "video_id", RejectionReason.INVALID_FORMAT, f"video_id 파싱 불가: {row.get('video_id', '누락')}", now))
            return None

    def _parse_enum(self, row: dict, field: str, enum_cls: type, source_id: str, task_id: str, rejections: list, now: datetime):
        try:
            return enum_cls(row[field])
        except KeyError:
            rejections.append(self._reject(task_id, source_id, field, RejectionReason.MISSING_REQUIRED_FIELD, f"{field} 누락", now))
            return None
        except ValueError:
            rejections.append(self._reject(task_id, source_id, field, RejectionReason.INVALID_ENUM_VALUE, f"알 수 없는 {field}: {row.get(field)}", now))
            return None

    @staticmethod
    def _reject(task_id: str, source_id: str, field: str, reason: RejectionReason, detail: str, now: datetime) -> Rejection:
        return Rejection(
            task_id=task_id, stage=Stage.ODD_TAGGING, reason=reason,
            source_id=source_id, field=field, detail=detail, created_at=now,
        )
