"""MySQL Repository 테스트 — SQLite in-memory DB 사용

주의: prefix_with("IGNORE")는 MySQL 전용이므로,
Selection/OddTag/Label의 save_all은 add_all + flush 방식으로 테스트한다.
Rejection은 원래 add_all 방식을 사용하므로 그대로 테스트한다.
"""

from datetime import datetime

from sqlalchemy import insert

from app.adapter.outbound.mysql.entities import (
    LabelEntity,
    OddTagEntity,
    RejectionEntity,
    SelectionEntity,
)
from app.adapter.outbound.mysql.mappers import (
    LabelMapper,
    OddTagMapper,
    RejectionMapper,
    SelectionMapper,
)
from app.adapter.outbound.mysql.repositories import (
    SqlLabelRepository,
    SqlOddTagRepository,
    SqlRejectionRepository,
    SqlSelectionRepository,
)
from app.domain.enums import (
    ObjectClass,
    RejectionReason,
    RoadSurface,
    Stage,
    TimeOfDay,
    Weather,
)
from app.domain.models import RejectionCriteria

from tests.adapter.conftest import (
    TASK_ID,
    make_label,
    make_odd_tag,
    make_rejection,
    make_selection,
)


# === 헬퍼: SQLite 호환 직접 insert ===


def _insert_selection(session, selection):
    """SQLite에서 prefix_with("IGNORE") 대신 직접 insert한다."""
    d = SelectionMapper.to_dict(selection)
    session.execute(insert(SelectionEntity).values(**d))
    session.flush()


def _insert_odd_tag(session, odd_tag):
    d = OddTagMapper.to_dict(odd_tag)
    session.execute(insert(OddTagEntity).values(**d))
    session.flush()


def _insert_label(session, label):
    d = LabelMapper.to_dict(label)
    session.execute(insert(LabelEntity).values(**d))
    session.flush()


# === SqlSelectionRepository ===


class TestSqlSelectionRepository:
    def test_find_by_id(self, db_session):
        selection = make_selection(video_id=100)
        _insert_selection(db_session, selection)

        repo = SqlSelectionRepository(db_session)
        found = repo.find_by_id(100)

        assert found is not None
        assert found.id.value == 100
        assert found.task_id == TASK_ID

    def test_find_by_id_not_found(self, db_session):
        repo = SqlSelectionRepository(db_session)
        assert repo.find_by_id(9999) is None

    def test_find_all_ids_by_task(self, db_session):
        for vid in [1, 2, 3]:
            _insert_selection(db_session, make_selection(video_id=vid))
        _insert_selection(db_session, make_selection(video_id=99, task_id="other-task"))

        repo = SqlSelectionRepository(db_session)
        ids = repo.find_all_ids_by_task(TASK_ID)

        assert ids == {1, 2, 3}


# === SqlOddTagRepository ===


class TestSqlOddTagRepository:
    def test_find_by_video_id(self, db_session):
        # OddTag는 video_id로 Selection과 연결
        _insert_selection(db_session, make_selection(video_id=10))
        _insert_odd_tag(db_session, make_odd_tag(video_id=10, weather=Weather.RAINY))

        repo = SqlOddTagRepository(db_session)
        found = repo.find_by_video_id(10)

        assert found is not None
        assert found.video_id.value == 10
        assert found.weather == Weather.RAINY

    def test_find_by_video_id_not_found(self, db_session):
        repo = SqlOddTagRepository(db_session)
        assert repo.find_by_video_id(9999) is None

    def test_find_all_video_ids_by_task(self, db_session):
        for vid in [1, 2, 3]:
            _insert_selection(db_session, make_selection(video_id=vid))
            _insert_odd_tag(db_session, make_odd_tag(odd_id=vid, video_id=vid))

        repo = SqlOddTagRepository(db_session)
        ids = repo.find_all_video_ids_by_task(TASK_ID)

        assert ids == {1, 2, 3}


# === SqlLabelRepository ===


class TestSqlLabelRepository:
    def test_find_all_by_video_id(self, db_session):
        _insert_selection(db_session, make_selection(video_id=50))
        _insert_label(db_session, make_label(video_id=50, object_class=ObjectClass.CAR))
        _insert_label(db_session, make_label(video_id=50, object_class=ObjectClass.PEDESTRIAN))

        repo = SqlLabelRepository(db_session)
        labels = repo.find_all_by_video_id(50)

        assert len(labels) == 2
        classes = {lb.object_class for lb in labels}
        assert classes == {ObjectClass.CAR, ObjectClass.PEDESTRIAN}

    def test_find_all_video_ids_by_task(self, db_session):
        for vid in [10, 20, 30]:
            _insert_selection(db_session, make_selection(video_id=vid))
            _insert_label(db_session, make_label(video_id=vid))

        repo = SqlLabelRepository(db_session)
        ids = repo.find_all_video_ids_by_task(TASK_ID)

        assert ids == {10, 20, 30}


# === SqlRejectionRepository ===


class TestSqlRejectionRepository:
    def test_save_all_and_search(self, db_session):
        rejections = [
            make_rejection(source_id="row-001", field="temperature"),
            make_rejection(source_id="row-002", field="recorded_at"),
        ]

        repo = SqlRejectionRepository(db_session)
        repo.save_all(rejections)

        criteria = RejectionCriteria(task_id=TASK_ID)
        results, total = repo.search(criteria)

        assert total == 2
        assert len(results) == 2

    def test_search_by_stage(self, db_session):
        repo = SqlRejectionRepository(db_session)
        repo.save_all([
            make_rejection(stage=Stage.SELECTION, source_id="s1"),
            make_rejection(stage=Stage.ODD_TAGGING, source_id="s2", reason=RejectionReason.DUPLICATE_TAGGING),
        ])

        criteria = RejectionCriteria(task_id=TASK_ID, stage=Stage.SELECTION)
        results, total = repo.search(criteria)

        assert total == 1
        assert results[0].stage == Stage.SELECTION

    def test_search_by_reason(self, db_session):
        repo = SqlRejectionRepository(db_session)
        repo.save_all([
            make_rejection(reason=RejectionReason.INVALID_FORMAT, source_id="r1"),
            make_rejection(reason=RejectionReason.MISSING_REQUIRED_FIELD, source_id="r2"),
        ])

        criteria = RejectionCriteria(reason=RejectionReason.INVALID_FORMAT)
        results, total = repo.search(criteria)

        assert total == 1
        assert results[0].reason == RejectionReason.INVALID_FORMAT

    def test_search_by_source_id_and_field(self, db_session):
        repo = SqlRejectionRepository(db_session)
        repo.save_all([
            make_rejection(source_id="src-A", field="temperature"),
            make_rejection(source_id="src-B", field="weather"),
        ])

        criteria = RejectionCriteria(source_id="src-A", field="temperature")
        results, total = repo.search(criteria)

        assert total == 1
        assert results[0].source_id == "src-A"
        assert results[0].field == "temperature"

    def test_search_pagination(self, db_session):
        repo = SqlRejectionRepository(db_session)
        repo.save_all([
            make_rejection(source_id=f"row-{i:03d}")
            for i in range(1, 6)
        ])

        # 1페이지, 사이즈 2
        criteria = RejectionCriteria(task_id=TASK_ID, page=1, size=2)
        results, total = repo.search(criteria)

        assert total == 5
        assert len(results) == 2

        # 3페이지, 사이즈 2 → 마지막 1건
        criteria = RejectionCriteria(task_id=TASK_ID, page=3, size=2)
        results, total = repo.search(criteria)

        assert total == 5
        assert len(results) == 1

    def test_search_empty(self, db_session):
        repo = SqlRejectionRepository(db_session)

        criteria = RejectionCriteria(task_id="non-existent")
        results, total = repo.search(criteria)

        assert total == 0
        assert results == []
