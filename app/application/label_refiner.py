from datetime import datetime

from app.domain.enums import ObjectClass, RejectionReason, Stage
from app.domain.models import Label, Rejection
from app.domain.value_objects import Confidence, ObjectCount, VideoId


class LabelRefiner:
    """자동 라벨링 원본 데이터를 도메인 모델로 정제한다.

    모든 필드를 검증하고, 에러가 여러 개면 에러별로 각각 Rejection을 생성한다.
    중복 탐지는 MySQL UNIQUE 제약에 위임한다.
    """

    def refine_single(self, task_id: str, row: dict) -> Label | list[Rejection]:
        rejections: list[Rejection] = []
        source_id = f"{row.get('video_id', '?')}:{row.get('object_class', '?')}"
        now = datetime.now()

        video_id = self._parse_video_id(row, source_id, task_id, rejections, now)
        object_class = self._parse_enum(row, "object_class", ObjectClass, source_id, task_id, rejections, now)
        obj_count = self._parse_obj_count(row, source_id, task_id, rejections, now)
        confidence = self._parse_confidence(row, source_id, task_id, rejections, now)
        labeled_at = self._parse_datetime(row, "labeled_at", source_id, task_id, rejections, now)

        if rejections:
            return rejections

        return Label(
            task_id=task_id, video_id=video_id, object_class=object_class,
            obj_count=obj_count, confidence=confidence, labeled_at=labeled_at,
        )

    def _parse_video_id(self, row: dict, source_id: str, task_id: str, rejections: list, now: datetime) -> VideoId | None:
        try:
            return VideoId(int(row["video_id"]))
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

    def _parse_obj_count(self, row: dict, source_id: str, task_id: str, rejections: list, now: datetime) -> ObjectCount | None:
        try:
            raw = float(row["obj_count"])
        except (ValueError, KeyError, TypeError):
            rejections.append(self._reject(task_id, source_id, "obj_count", RejectionReason.INVALID_FORMAT, f"obj_count 파싱 불가: {row.get('obj_count', '누락')}", now))
            return None
        if raw != int(raw):
            rejections.append(self._reject(task_id, source_id, "obj_count", RejectionReason.FRACTIONAL_OBJ_COUNT, f"obj_count가 소수점: {row['obj_count']}", now))
            return None
        try:
            return ObjectCount(int(raw))
        except (ValueError, TypeError) as e:
            rejections.append(self._reject(task_id, source_id, "obj_count", RejectionReason.NEGATIVE_OBJ_COUNT, str(e), now))
            return None

    def _parse_confidence(self, row: dict, source_id: str, task_id: str, rejections: list, now: datetime) -> Confidence | None:
        try:
            return Confidence(float(row["avg_confidence"]))
        except (ValueError, KeyError, TypeError):
            rejections.append(self._reject(task_id, source_id, "avg_confidence", RejectionReason.INVALID_FORMAT, f"avg_confidence 파싱 불가: {row.get('avg_confidence', '누락')}", now))
            return None

    def _parse_datetime(self, row: dict, field: str, source_id: str, task_id: str, rejections: list, now: datetime) -> datetime | None:
        try:
            return datetime.fromisoformat(row[field])
        except (ValueError, KeyError, TypeError):
            rejections.append(self._reject(task_id, source_id, field, RejectionReason.INVALID_FORMAT, f"{field} 파싱 불가: {row.get(field, '누락')}", now))
            return None

    @staticmethod
    def _reject(task_id: str, source_id: str, field: str, reason: RejectionReason, detail: str, now: datetime) -> Rejection:
        return Rejection(
            task_id=task_id, stage=Stage.AUTO_LABELING, reason=reason,
            source_id=source_id, field=field, detail=detail, created_at=now,
        )
