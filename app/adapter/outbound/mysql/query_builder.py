from sqlalchemy import Select, and_, func, select

from app.adapter.outbound.mysql.entities import (
    LabelEntity,
    OddTagEntity,
    RejectionEntity,
    SelectionEntity,
)
from app.domain.models import DataSearchCriteria, RejectionCriteria


class DataSearchQueryBuilder:
    """학습 데이터 검색 쿼리 빌더

    동적 조건(Selection + ODD + Label)을 조합하여 SELECT/COUNT 쿼리를 생성한다.
    """

    def __init__(self, criteria: DataSearchCriteria) -> None:
        self._criteria = criteria

    def build_query(self) -> Select:
        stmt = select(SelectionEntity)
        stmt = self._apply_selection_conditions(stmt)
        stmt = self._apply_odd_conditions(stmt)
        stmt = self._apply_label_conditions(stmt)
        stmt = self._apply_pagination(stmt)
        return stmt

    def build_count_query(self) -> Select:
        stmt = select(func.count()).select_from(SelectionEntity)
        stmt = self._apply_selection_conditions(stmt)
        stmt = self._apply_odd_conditions(stmt)
        stmt = self._apply_label_conditions(stmt)
        return stmt

    def _apply_selection_conditions(self, stmt: Select) -> Select:
        c = self._criteria
        if c.task_id is not None:
            stmt = stmt.where(SelectionEntity.task_id == c.task_id)
        if c.recorded_at_from is not None:
            stmt = stmt.where(SelectionEntity.recorded_at >= c.recorded_at_from)
        if c.recorded_at_to is not None:
            stmt = stmt.where(SelectionEntity.recorded_at <= c.recorded_at_to)
        if c.min_temperature is not None:
            stmt = stmt.where(SelectionEntity.temperature_celsius >= c.min_temperature)
        if c.max_temperature is not None:
            stmt = stmt.where(SelectionEntity.temperature_celsius <= c.max_temperature)
        if c.headlights_on is not None:
            stmt = stmt.where(SelectionEntity.headlights_on == c.headlights_on)
        return stmt

    def _apply_odd_conditions(self, stmt: Select) -> Select:
        c = self._criteria
        if not any([c.weather, c.time_of_day, c.road_surface]):
            return stmt

        stmt = stmt.join(OddTagEntity, SelectionEntity.id == OddTagEntity.video_id)

        if c.weather is not None:
            stmt = stmt.where(OddTagEntity.weather == c.weather.value)
        if c.time_of_day is not None:
            stmt = stmt.where(OddTagEntity.time_of_day == c.time_of_day.value)
        if c.road_surface is not None:
            stmt = stmt.where(OddTagEntity.road_surface == c.road_surface.value)

        return stmt

    def _apply_label_conditions(self, stmt: Select) -> Select:
        c = self._criteria
        if not any([c.object_class, c.min_obj_count, c.min_confidence]):
            return stmt

        conditions = [LabelEntity.video_id == SelectionEntity.id]
        if c.object_class is not None:
            conditions.append(LabelEntity.object_class == c.object_class.value)
        if c.min_obj_count is not None:
            conditions.append(LabelEntity.obj_count >= c.min_obj_count)
        if c.min_confidence is not None:
            conditions.append(LabelEntity.avg_confidence >= c.min_confidence)

        exists_subquery = select(LabelEntity.id).where(and_(*conditions)).exists()
        stmt = stmt.where(exists_subquery)

        return stmt

    def _apply_pagination(self, stmt: Select) -> Select:
        c = self._criteria
        stmt = stmt.order_by(SelectionEntity.id)
        if c.after is not None:
            stmt = stmt.where(SelectionEntity.id > c.after)
        elif c.page is not None:
            stmt = stmt.offset((c.page - 1) * c.size)
        return stmt.limit(c.size)


class RejectionQueryBuilder:
    """거부 데이터 조회 쿼리 빌더

    task_id, stage, reason 필터 조건을 동적으로 조합한다.
    """

    def __init__(self, criteria: RejectionCriteria) -> None:
        self._criteria = criteria

    def build_query(self) -> Select:
        stmt = select(RejectionEntity)
        stmt = self._apply_filters(stmt)
        stmt = self._apply_pagination(stmt)
        return stmt

    def build_count_query(self) -> Select:
        stmt = select(func.count()).select_from(RejectionEntity)
        stmt = self._apply_filters(stmt)
        return stmt

    def _apply_filters(self, stmt: Select) -> Select:
        c = self._criteria
        if c.task_id is not None:
            stmt = stmt.where(RejectionEntity.task_id == c.task_id)
        if c.stage is not None:
            stmt = stmt.where(RejectionEntity.stage == c.stage.value)
        if c.reason is not None:
            stmt = stmt.where(RejectionEntity.reason == c.reason.value)
        if c.source_id is not None:
            stmt = stmt.where(RejectionEntity.source_id == c.source_id)
        if c.field is not None:
            stmt = stmt.where(RejectionEntity.field == c.field)
        return stmt

    def _apply_pagination(self, stmt: Select) -> Select:
        c = self._criteria
        stmt = stmt.order_by(RejectionEntity.id)
        if c.after is not None:
            stmt = stmt.where(RejectionEntity.id > c.after)
        elif c.page is not None:
            stmt = stmt.offset((c.page - 1) * c.size)
        return stmt.limit(c.size)
