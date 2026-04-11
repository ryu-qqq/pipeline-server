"""QueryBuilder 테스트 — SQL 구문을 MySQL 방언으로 컴파일하여 조건절/페이지네이션을 검증한다."""

from datetime import datetime

from app.adapter.outbound.mysql.query_builder import (
    DataSearchQueryBuilder,
    RejectionQueryBuilder,
)
from app.domain.enums import (
    ObjectClass,
    RejectionReason,
    RoadSurface,
    Stage,
    TimeOfDay,
    Weather,
)
from app.domain.models import DataSearchCriteria, RejectionCriteria


def _compile_sql(stmt) -> str:
    """SQLAlchemy Select를 MySQL 방언으로 컴파일한 SQL 문자열을 반환한다."""
    from sqlalchemy.dialects import mysql

    return str(stmt.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))


# === DataSearchQueryBuilder ===


class TestDataSearchQueryBuilder:
    def test_task_id_filter(self):
        criteria = DataSearchCriteria(task_id="task-001")
        builder = DataSearchQueryBuilder(criteria)

        sql = _compile_sql(builder.build_query())

        assert "task_id" in sql
        assert "'task-001'" in sql

    def test_recorded_at_range(self):
        criteria = DataSearchCriteria(
            recorded_at_from=datetime(2024, 1, 1),
            recorded_at_to=datetime(2024, 12, 31),
        )
        builder = DataSearchQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        assert "recorded_at >=" in sql
        assert "recorded_at <=" in sql

    def test_temperature_range(self):
        criteria = DataSearchCriteria(min_temperature=-5.0, max_temperature=30.0)
        builder = DataSearchQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        assert "temperature_celsius >= -5.0" in sql
        assert "temperature_celsius <= 30.0" in sql

    def test_headlights_filter(self):
        criteria = DataSearchCriteria(headlights_on=True)
        builder = DataSearchQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        assert "headlights_on" in sql

    def test_odd_conditions_join(self):
        criteria = DataSearchCriteria(
            weather=Weather.RAINY,
            time_of_day=TimeOfDay.NIGHT,
            road_surface=RoadSurface.WET,
        )
        builder = DataSearchQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        assert "JOIN" in sql or "join" in sql.lower()
        assert "odd_tags" in sql
        assert "'rainy'" in sql
        assert "'night'" in sql
        assert "'wet'" in sql

    def test_label_subquery(self):
        criteria = DataSearchCriteria(
            object_class=ObjectClass.CAR,
            min_obj_count=3,
            min_confidence=0.8,
        )
        builder = DataSearchQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        assert "labels" in sql
        assert "'car'" in sql
        assert "obj_count >= 3" in sql
        assert "avg_confidence >= 0.8" in sql
        assert "EXISTS" in sql

    def test_pagination(self):
        criteria = DataSearchCriteria(page=3, size=10)
        builder = DataSearchQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        # MySQL LIMIT 문법: LIMIT offset, count → LIMIT 20, 10
        assert "LIMIT 20, 10" in sql

    def test_count_query_has_no_pagination(self):
        criteria = DataSearchCriteria(task_id="task-001", page=2, size=10)
        builder = DataSearchQueryBuilder(criteria)
        sql = _compile_sql(builder.build_count_query())

        assert "count" in sql.lower()
        assert "LIMIT" not in sql
        assert "OFFSET" not in sql

    def test_no_conditions(self):
        criteria = DataSearchCriteria()
        builder = DataSearchQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        # WHERE 절 없이 selections 테이블만 조회
        assert "selections" in sql
        assert "odd_tags" not in sql
        assert "labels" not in sql


# === RejectionQueryBuilder ===


class TestRejectionQueryBuilder:
    def test_task_id_filter(self):
        criteria = RejectionCriteria(task_id="task-rej-001")
        builder = RejectionQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        assert "'task-rej-001'" in sql

    def test_stage_filter(self):
        criteria = RejectionCriteria(stage=Stage.SELECTION)
        builder = RejectionQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        assert "'selection'" in sql

    def test_reason_filter(self):
        criteria = RejectionCriteria(reason=RejectionReason.INVALID_FORMAT)
        builder = RejectionQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        assert "'invalid_format'" in sql

    def test_source_id_filter(self):
        criteria = RejectionCriteria(source_id="src-99")
        builder = RejectionQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        assert "'src-99'" in sql

    def test_field_filter(self):
        criteria = RejectionCriteria(field="temperature")
        builder = RejectionQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        assert "'temperature'" in sql

    def test_combined_filters(self):
        criteria = RejectionCriteria(
            task_id="task-001",
            stage=Stage.ODD_TAGGING,
            reason=RejectionReason.DUPLICATE_TAGGING,
            source_id="odd-55",
            field="weather",
        )
        builder = RejectionQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        assert "'task-001'" in sql
        assert "'odd_tagging'" in sql
        assert "'duplicate_tagging'" in sql
        assert "'odd-55'" in sql
        assert "'weather'" in sql

    def test_pagination(self):
        criteria = RejectionCriteria(page=2, size=15)
        builder = RejectionQueryBuilder(criteria)
        sql = _compile_sql(builder.build_query())

        # MySQL LIMIT 문법: LIMIT offset, count → LIMIT 15, 15
        assert "LIMIT 15, 15" in sql

    def test_count_query(self):
        criteria = RejectionCriteria(task_id="task-001")
        builder = RejectionQueryBuilder(criteria)
        sql = _compile_sql(builder.build_count_query())

        assert "count" in sql.lower()
        assert "LIMIT" not in sql
        assert "OFFSET" not in sql
