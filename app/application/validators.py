import json
from collections import Counter
from datetime import datetime

from app.domain.enums import (
    ObjectClass,
    RejectionReason,
    RoadSurface,
    Stage,
    TimeOfDay,
    Weather,
)
from app.domain.exceptions import DomainError
from app.domain.models import Label, OddTag, Rejection
from app.domain.value_objects import Confidence, ObjectCount, VideoId


class OddValidator:
    """ODD 태깅 데이터 검증기"""

    def validate_batch(self, rows: list[dict], valid_video_ids: set[int]) -> tuple[list[OddTag], list[Rejection]]:
        now = datetime.now()
        valid: list[OddTag] = []
        rejected: list[Rejection] = []

        per_record_valid: list[tuple[dict, OddTag]] = []
        for row in rows:
            result = self._validate_single(row, valid_video_ids, now)
            if isinstance(result, Rejection):
                rejected.append(result)
            else:
                per_record_valid.append((row, result))

        video_id_counts = Counter(odd.video_id for _, odd in per_record_valid)
        duplicate_video_ids = {vid for vid, cnt in video_id_counts.items() if cnt > 1}

        for raw, odd in per_record_valid:
            if odd.video_id in duplicate_video_ids:
                rejected.append(
                    Rejection(
                        record_identifier=f"video_id={odd.video_id.value}",
                        stage=Stage.ODD_TAGGING,
                        reason=RejectionReason.DUPLICATE_TAGGING,
                        detail=f"동일 video_id에 {video_id_counts[odd.video_id]}건의 태깅 존재",
                        raw_data=json.dumps(raw, ensure_ascii=False),
                        created_at=now,
                    )
                )
            else:
                valid.append(odd)

        return valid, rejected

    def _validate_single(self, row: dict, valid_video_ids: set[int], now: datetime) -> OddTag | Rejection:
        raw_video_id = str(row.get("video_id", ""))
        identifier = f"odd_id={row.get('id', '?')}"

        try:
            video_id = VideoId(int(raw_video_id.lstrip("0") or "0"))
        except (ValueError, TypeError):
            return Rejection(
                record_identifier=identifier,
                stage=Stage.ODD_TAGGING,
                reason=RejectionReason.INVALID_FORMAT,
                detail=f"video_id 파싱 불가: {raw_video_id}",
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        try:
            odd_id = int(row["id"])
        except (ValueError, KeyError, TypeError):
            return Rejection(
                record_identifier=identifier,
                stage=Stage.ODD_TAGGING,
                reason=RejectionReason.INVALID_FORMAT,
                detail=f"id 파싱 불가: {row.get('id')}",
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        try:
            weather = Weather(row["weather"])
        except (ValueError, KeyError):
            return Rejection(
                record_identifier=identifier,
                stage=Stage.ODD_TAGGING,
                reason=RejectionReason.INVALID_ENUM_VALUE,
                detail=f"알 수 없는 weather: {row.get('weather')}",
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        try:
            time_of_day = TimeOfDay(row["time_of_day"])
        except (ValueError, KeyError):
            return Rejection(
                record_identifier=identifier,
                stage=Stage.ODD_TAGGING,
                reason=RejectionReason.INVALID_ENUM_VALUE,
                detail=f"알 수 없는 time_of_day: {row.get('time_of_day')}",
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        try:
            road_surface = RoadSurface(row["road_surface"])
        except (ValueError, KeyError):
            return Rejection(
                record_identifier=identifier,
                stage=Stage.ODD_TAGGING,
                reason=RejectionReason.INVALID_ENUM_VALUE,
                detail=f"알 수 없는 road_surface: {row.get('road_surface')}",
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        return OddTag(
            id=odd_id,
            video_id=video_id,
            weather=weather,
            time_of_day=time_of_day,
            road_surface=road_surface,
        )


class LabelValidator:
    """자동 라벨링 데이터 검증기"""

    def validate_batch(self, rows: list[dict], valid_video_ids: set[int]) -> tuple[list[Label], list[Rejection]]:
        now = datetime.now()
        valid: list[Label] = []
        rejected: list[Rejection] = []

        per_record_valid: list[tuple[dict, Label]] = []
        for row in rows:
            result = self._validate_single(row, valid_video_ids, now)
            if isinstance(result, Rejection):
                rejected.append(result)
            else:
                per_record_valid.append((row, result))

        key_counts = Counter((label.video_id, label.object_class) for _, label in per_record_valid)
        duplicate_keys = {k for k, cnt in key_counts.items() if cnt > 1}

        for raw, label in per_record_valid:
            key = (label.video_id, label.object_class)
            if key in duplicate_keys:
                rejected.append(
                    Rejection(
                        record_identifier=f"video_id={label.video_id.value},class={label.object_class.value}",
                        stage=Stage.AUTO_LABELING,
                        reason=RejectionReason.DUPLICATE_LABEL,
                        detail=f"동일 video_id+class에 {key_counts[key]}건의 라벨 존재",
                        raw_data=json.dumps(raw, ensure_ascii=False),
                        created_at=now,
                    )
                )
            else:
                valid.append(label)

        return valid, rejected

    def _validate_single(self, row: dict, valid_video_ids: set[int], now: datetime) -> Label | Rejection:
        identifier = f"video_id={row.get('video_id', '?')},class={row.get('object_class', '?')}"

        try:
            video_id = VideoId(int(row["video_id"]))
        except (ValueError, KeyError, TypeError):
            return Rejection(
                record_identifier=identifier,
                stage=Stage.AUTO_LABELING,
                reason=RejectionReason.INVALID_FORMAT,
                detail=f"video_id 파싱 불가: {row.get('video_id')}",
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        try:
            object_class = ObjectClass(row["object_class"])
        except (ValueError, KeyError):
            return Rejection(
                record_identifier=identifier,
                stage=Stage.AUTO_LABELING,
                reason=RejectionReason.INVALID_ENUM_VALUE,
                detail=f"알 수 없는 object_class: {row.get('object_class')}",
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        try:
            obj_count_raw = float(row["obj_count"])
        except (ValueError, KeyError, TypeError):
            return Rejection(
                record_identifier=identifier,
                stage=Stage.AUTO_LABELING,
                reason=RejectionReason.INVALID_FORMAT,
                detail=f"obj_count 파싱 불가: {row.get('obj_count')}",
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        if obj_count_raw != int(obj_count_raw):
            return Rejection(
                record_identifier=identifier,
                stage=Stage.AUTO_LABELING,
                reason=RejectionReason.FRACTIONAL_OBJ_COUNT,
                detail=f"obj_count가 소수점: {row['obj_count']}",
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        try:
            obj_count = ObjectCount(int(obj_count_raw))
        except (DomainError, ValueError, TypeError) as e:
            return Rejection(
                record_identifier=identifier,
                stage=Stage.AUTO_LABELING,
                reason=RejectionReason.NEGATIVE_OBJ_COUNT,
                detail=str(e),
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        try:
            confidence = Confidence(float(row["avg_confidence"]))
        except (ValueError, KeyError, TypeError):
            return Rejection(
                record_identifier=identifier,
                stage=Stage.AUTO_LABELING,
                reason=RejectionReason.INVALID_FORMAT,
                detail=f"avg_confidence 파싱 불가: {row.get('avg_confidence')}",
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        try:
            labeled_at = datetime.fromisoformat(row["labeled_at"])
        except (ValueError, KeyError, TypeError):
            return Rejection(
                record_identifier=identifier,
                stage=Stage.AUTO_LABELING,
                reason=RejectionReason.INVALID_FORMAT,
                detail=f"labeled_at 파싱 불가: {row.get('labeled_at')}",
                raw_data=json.dumps(row, ensure_ascii=False),
                created_at=now,
            )

        return Label(
            video_id=video_id,
            object_class=object_class,
            obj_count=obj_count,
            confidence=confidence,
            labeled_at=labeled_at,
        )
