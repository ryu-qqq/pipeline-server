from datetime import datetime

from app.adapter.outbound.entities import (
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


class SelectionMapper:
    @staticmethod
    def to_entity(domain: Selection) -> SelectionEntity:
        return SelectionEntity(
            id=domain.id,
            recorded_at=domain.recorded_at,
            temperature_celsius=domain.temperature_celsius,
            wiper_active=domain.wiper_active,
            wiper_level=domain.wiper_level,
            headlights_on=domain.headlights_on,
            source_path=domain.source_path,
        )

    @staticmethod
    def to_domain(entity: SelectionEntity) -> Selection:
        return Selection(
            id=entity.id,
            recorded_at=entity.recorded_at,
            temperature_celsius=entity.temperature_celsius,
            wiper_active=entity.wiper_active,
            wiper_level=entity.wiper_level,
            headlights_on=entity.headlights_on,
            source_path=entity.source_path,
        )


class OddTagMapper:
    @staticmethod
    def to_entity(domain: OddTag) -> OddTagEntity:
        return OddTagEntity(
            id=domain.id,
            video_id=domain.video_id,
            weather=domain.weather.value,
            time_of_day=domain.time_of_day.value,
            road_surface=domain.road_surface.value,
        )

    @staticmethod
    def to_domain(entity: OddTagEntity) -> OddTag:
        return OddTag(
            id=entity.id,
            video_id=entity.video_id,
            weather=Weather(entity.weather),
            time_of_day=TimeOfDay(entity.time_of_day),
            road_surface=RoadSurface(entity.road_surface),
        )


class LabelMapper:
    @staticmethod
    def to_entity(domain: Label) -> LabelEntity:
        return LabelEntity(
            video_id=domain.video_id,
            object_class=domain.object_class.value,
            obj_count=domain.obj_count,
            avg_confidence=domain.avg_confidence,
            labeled_at=domain.labeled_at,
        )

    @staticmethod
    def to_domain(entity: LabelEntity) -> Label:
        return Label(
            video_id=entity.video_id,
            object_class=ObjectClass(entity.object_class),
            obj_count=entity.obj_count,
            avg_confidence=entity.avg_confidence,
            labeled_at=entity.labeled_at,
        )


class RejectionMapper:
    @staticmethod
    def to_entity(domain: Rejection) -> RejectionEntity:
        return RejectionEntity(
            record_identifier=domain.record_identifier,
            stage=domain.stage.value,
            reason=domain.reason.value,
            detail=domain.detail,
            raw_data=domain.raw_data,
            created_at=domain.created_at,
        )

    @staticmethod
    def to_domain(entity: RejectionEntity) -> Rejection:
        return Rejection(
            record_identifier=entity.record_identifier,
            stage=Stage(entity.stage),
            reason=RejectionReason(entity.reason),
            detail=entity.detail,
            raw_data=entity.raw_data or "",
            created_at=entity.created_at or datetime.now(),
        )
