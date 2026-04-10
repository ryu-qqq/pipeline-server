from datetime import datetime

from app.adapter.outbound.mysql.entities import (
    LabelEntity,
    OddTagEntity,
    RejectionEntity,
    SelectionEntity,
)
from app.domain.enums import (
    ObjectClass,
    RejectionReason,
    RoadSurface,
    Stage,
    TimeOfDay,
    Weather,
)
from app.domain.models import Label, OddTag, Rejection, Selection
from app.domain.value_objects import Confidence, ObjectCount, SourcePath, Temperature, VideoId, WiperState


class SelectionMapper:
    @staticmethod
    def to_entity(domain: Selection) -> SelectionEntity:
        return SelectionEntity(
            id=domain.id.value,
            task_id=domain.task_id,
            recorded_at=domain.recorded_at,
            temperature_celsius=domain.temperature.celsius,
            wiper_active=domain.wiper.active,
            wiper_level=domain.wiper.level,
            headlights_on=domain.headlights_on,
            source_path=domain.source_path.value,
        )

    @staticmethod
    def to_dict(domain: Selection) -> dict:
        return {
            "id": domain.id.value,
            "task_id": domain.task_id,
            "recorded_at": domain.recorded_at,
            "temperature_celsius": domain.temperature.celsius,
            "wiper_active": domain.wiper.active,
            "wiper_level": domain.wiper.level,
            "headlights_on": domain.headlights_on,
            "source_path": domain.source_path.value,
        }

    @staticmethod
    def to_domain(entity: SelectionEntity) -> Selection:
        return Selection(
            id=VideoId(entity.id),
            task_id=entity.task_id,
            recorded_at=entity.recorded_at,
            temperature=Temperature.from_celsius(entity.temperature_celsius),
            wiper=WiperState(active=entity.wiper_active, level=entity.wiper_level),
            headlights_on=entity.headlights_on,
            source_path=SourcePath(entity.source_path),
        )


class OddTagMapper:
    @staticmethod
    def to_entity(domain: OddTag) -> OddTagEntity:
        return OddTagEntity(
            id=domain.id,
            task_id=domain.task_id,
            video_id=domain.video_id.value,
            weather=domain.weather.value,
            time_of_day=domain.time_of_day.value,
            road_surface=domain.road_surface.value,
        )

    @staticmethod
    def to_dict(domain: OddTag) -> dict:
        return {
            "task_id": domain.task_id,
            "video_id": domain.video_id.value,
            "weather": domain.weather.value,
            "time_of_day": domain.time_of_day.value,
            "road_surface": domain.road_surface.value,
        }

    @staticmethod
    def to_domain(entity: OddTagEntity) -> OddTag:
        return OddTag(
            id=entity.id,
            task_id=entity.task_id,
            video_id=VideoId(entity.video_id),
            weather=Weather(entity.weather),
            time_of_day=TimeOfDay(entity.time_of_day),
            road_surface=RoadSurface(entity.road_surface),
        )


class LabelMapper:
    @staticmethod
    def to_entity(domain: Label) -> LabelEntity:
        return LabelEntity(
            task_id=domain.task_id,
            video_id=domain.video_id.value,
            object_class=domain.object_class.value,
            obj_count=domain.obj_count.value,
            avg_confidence=domain.confidence.value,
            labeled_at=domain.labeled_at,
        )

    @staticmethod
    def to_dict(domain: Label) -> dict:
        return {
            "task_id": domain.task_id,
            "video_id": domain.video_id.value,
            "object_class": domain.object_class.value,
            "obj_count": domain.obj_count.value,
            "avg_confidence": domain.confidence.value,
            "labeled_at": domain.labeled_at,
        }

    @staticmethod
    def to_domain(entity: LabelEntity) -> Label:
        return Label(
            task_id=entity.task_id,
            video_id=VideoId(entity.video_id),
            object_class=ObjectClass(entity.object_class),
            obj_count=ObjectCount(entity.obj_count),
            confidence=Confidence(entity.avg_confidence),
            labeled_at=entity.labeled_at,
        )


class RejectionMapper:
    @staticmethod
    def to_entity(domain: Rejection) -> RejectionEntity:
        return RejectionEntity(
            task_id=domain.task_id,
            stage=domain.stage.value,
            reason=domain.reason.value,
            source_id=domain.source_id,
            field=domain.field,
            detail=domain.detail,
            created_at=domain.created_at,
        )

    @staticmethod
    def to_domain(entity: RejectionEntity) -> Rejection:
        return Rejection(
            task_id=entity.task_id,
            stage=Stage(entity.stage),
            reason=RejectionReason(entity.reason),
            source_id=entity.source_id,
            field=entity.field,
            detail=entity.detail,
            created_at=entity.created_at or datetime.now(),
        )
