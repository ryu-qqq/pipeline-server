"""MySQL Repository 테스트 — MySQL testcontainer 사용

INSERT IGNORE, 페이지네이션, 필터링 등 MySQL 고유 동작을 실제 DB에서 검증한다.
"""

from app.adapter.outbound.mysql.repositories import (
    SqlDataSearchRepository,
    SqlLabelRepository,
    SqlOddTagRepository,
    SqlRejectionRepository,
    SqlSelectionRepository,
)
from app.domain.enums import (
    ObjectClass,
    RejectionReason,
    Stage,
    Weather,
)
from app.domain.models import DataSearchCriteria, RejectionCriteria
from tests.adapter.conftest import (
    TASK_ID,
    make_label,
    make_odd_tag,
    make_rejection,
    make_selection,
)

# === SqlSelectionRepository ===


class TestSqlSelectionRepository:
    def test_save_all_and_find_by_id(self, db_session):
        """save_all 후 find_by_id로 조회한다"""
        repo = SqlSelectionRepository(db_session)
        selection = make_selection(video_id=100)

        inserted = repo.save_all([selection])
        assert inserted == 1

        found = repo.find_by_id(100)
        assert found is not None
        assert found.id.value == 100
        assert found.task_id == TASK_ID

    def test_find_by_id_not_found(self, db_session):
        repo = SqlSelectionRepository(db_session)
        assert repo.find_by_id(9999) is None

    def test_find_all_ids_by_task(self, db_session):
        repo = SqlSelectionRepository(db_session)
        repo.save_all([make_selection(video_id=v) for v in [1, 2, 3]])
        repo.save_all([make_selection(video_id=99, task_id="other-task")])

        ids = repo.find_all_ids_by_task(TASK_ID)
        assert ids == {1, 2, 3}

    def test_save_all_insert_ignore_중복_무시(self, db_session):
        """동일 video_id를 두 번 save_all하면 중복은 무시된다 (INSERT IGNORE)"""
        repo = SqlSelectionRepository(db_session)

        first = repo.save_all([make_selection(video_id=10)])
        assert first == 1

        second = repo.save_all([make_selection(video_id=10)])
        assert second == 0  # 중복이므로 0건 적재


# === SqlOddTagRepository ===


class TestSqlOddTagRepository:
    def test_save_all_and_find_by_video_id(self, db_session):
        sel_repo = SqlSelectionRepository(db_session)
        sel_repo.save_all([make_selection(video_id=10)])

        odd_repo = SqlOddTagRepository(db_session)
        inserted = odd_repo.save_all([make_odd_tag(video_id=10, weather=Weather.RAINY)])
        assert inserted == 1

        found = odd_repo.find_by_video_id(10)
        assert found is not None
        assert found.video_id.value == 10
        assert found.weather == Weather.RAINY

    def test_find_by_video_id_not_found(self, db_session):
        repo = SqlOddTagRepository(db_session)
        assert repo.find_by_video_id(9999) is None

    def test_find_all_video_ids_by_task(self, db_session):
        sel_repo = SqlSelectionRepository(db_session)
        odd_repo = SqlOddTagRepository(db_session)

        for vid in [1, 2, 3]:
            sel_repo.save_all([make_selection(video_id=vid)])
            odd_repo.save_all([make_odd_tag(odd_id=vid, video_id=vid)])

        ids = odd_repo.find_all_video_ids_by_task(TASK_ID)
        assert ids == {1, 2, 3}

    def test_save_all_insert_ignore_중복_무시(self, db_session):
        """동일 video_id의 OddTag를 두 번 save_all하면 중복은 무시된다"""
        sel_repo = SqlSelectionRepository(db_session)
        sel_repo.save_all([make_selection(video_id=20)])

        odd_repo = SqlOddTagRepository(db_session)
        first = odd_repo.save_all([make_odd_tag(video_id=20)])
        assert first == 1

        second = odd_repo.save_all([make_odd_tag(odd_id=99, video_id=20)])
        assert second == 0


# === SqlLabelRepository ===


class TestSqlLabelRepository:
    def test_save_all_and_find_all_by_video_id(self, db_session):
        sel_repo = SqlSelectionRepository(db_session)
        sel_repo.save_all([make_selection(video_id=50)])

        label_repo = SqlLabelRepository(db_session)
        inserted = label_repo.save_all([
            make_label(video_id=50, object_class=ObjectClass.CAR),
            make_label(video_id=50, object_class=ObjectClass.PEDESTRIAN),
        ])
        assert inserted == 2

        labels = label_repo.find_all_by_video_id(50)
        assert len(labels) == 2
        classes = {lb.object_class for lb in labels}
        assert classes == {ObjectClass.CAR, ObjectClass.PEDESTRIAN}

    def test_find_all_video_ids_by_task(self, db_session):
        sel_repo = SqlSelectionRepository(db_session)
        label_repo = SqlLabelRepository(db_session)

        for vid in [10, 20, 30]:
            sel_repo.save_all([make_selection(video_id=vid)])
            label_repo.save_all([make_label(video_id=vid)])

        ids = label_repo.find_all_video_ids_by_task(TASK_ID)
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


# === SqlDataSearchRepository ===


class TestSqlDataSearchRepository:
    def test_search_통합_결과_조합(self, db_session):
        """Selection + OddTag + Label이 올바르게 조합되어 반환된다"""
        sel_repo = SqlSelectionRepository(db_session)
        odd_repo = SqlOddTagRepository(db_session)
        label_repo = SqlLabelRepository(db_session)

        sel_repo.save_all([make_selection(video_id=1)])
        odd_repo.save_all([make_odd_tag(video_id=1, weather=Weather.SUNNY)])
        label_repo.save_all([make_label(video_id=1, object_class=ObjectClass.CAR)])

        search_repo = SqlDataSearchRepository(db_session)
        results, total = search_repo.search(DataSearchCriteria(task_id=TASK_ID))

        assert total == 1
        result = results[0]
        assert result.selection.id.value == 1
        assert result.odd_tag is not None
        assert result.odd_tag.weather == Weather.SUNNY
        assert len(result.labels) == 1
        assert result.labels[0].object_class == ObjectClass.CAR

    def test_search_빈_결과(self, db_session):
        search_repo = SqlDataSearchRepository(db_session)
        results, total = search_repo.search(DataSearchCriteria(task_id="non-existent"))

        assert total == 0
        assert results == []
