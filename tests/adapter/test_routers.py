"""REST 라우터 테스트 — FastAPI TestClient + DI override"""

from datetime import datetime

from app.domain.enums import (
    RejectionReason,
    Stage,
    TaskStatus,
)
from app.domain.exceptions import ConflictError, DataNotFoundError
from app.domain.models import (
    AnalysisResult,
    AnalyzeTask,
    SearchResult,
)
from app.domain.value_objects import StageProgress, StageResult
from tests.adapter.conftest import make_label, make_odd_tag, make_rejection, make_selection

# === POST /analyze ===


class TestPostAnalyze:
    def test_returns_202_with_task_id(self, test_client, mock_analysis_service):
        mock_analysis_service.submit.return_value = "task-abc-123"

        resp = test_client.post("/analyze")

        assert resp.status_code == 202
        body = resp.json()
        assert body["data"]["task_id"] == "task-abc-123"
        assert body["data"]["status"] == TaskStatus.PENDING
        mock_analysis_service.submit.assert_called_once()

    def test_conflict_시_409_반환(self, test_client, mock_analysis_service):
        """이미 진행 중인 작업이 있으면 ConflictError → 409 응답"""
        mock_analysis_service.submit.side_effect = ConflictError("이미 진행 중인 작업이 있습니다")

        resp = test_client.post("/analyze")

        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "CONFLICT"
        assert "진행 중" in body["detail"]


# === GET /analyze/{task_id} ===


class TestGetTaskStatus:
    def test_returns_200_with_progress(self, test_client, mock_task_read_service):
        task = AnalyzeTask(
            task_id="task-abc-123",
            status=TaskStatus.PROCESSING,
            selection_progress=StageProgress(total=100, processed=50, rejected=5),
            odd_tagging_progress=StageProgress(total=95, processed=30, rejected=2),
            auto_labeling_progress=StageProgress(total=93, processed=0, rejected=0),
            created_at=datetime(2024, 6, 1, 12, 0, 0),
        )
        mock_task_read_service.get_task.return_value = task

        resp = test_client.get("/analyze/task-abc-123")

        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert data["task_id"] == "task-abc-123"
        assert data["status"] == TaskStatus.PROCESSING

        progress = data["progress"]
        assert progress["selection"]["total"] == 100
        assert progress["selection"]["processed"] == 50
        assert progress["selection"]["rejected"] == 5
        assert progress["selection"]["percent"] == 55.0

        assert progress["odd_tagging"]["total"] == 95
        assert progress["auto_labeling"]["total"] == 93

        mock_task_read_service.get_task.assert_called_once_with("task-abc-123")

    def test_returns_completed_task_with_result(self, test_client, mock_task_read_service):
        task = AnalyzeTask(
            task_id="task-done",
            status=TaskStatus.COMPLETED,
            selection_progress=StageProgress(total=100, processed=95, rejected=5),
            odd_tagging_progress=StageProgress(total=95, processed=93, rejected=2),
            auto_labeling_progress=StageProgress(total=93, processed=93, rejected=0),
            result=AnalysisResult(
                selection=StageResult(total=100, loaded=95, rejected=5),
                odd_tagging=StageResult(total=95, loaded=93, rejected=2),
                auto_labeling=StageResult(total=93, loaded=93, rejected=0),
                fully_linked=90,
                partial=3,
            ),
            created_at=datetime(2024, 6, 1, 12, 0, 0),
            completed_at=datetime(2024, 6, 1, 13, 0, 0),
        )
        mock_task_read_service.get_task.return_value = task

        resp = test_client.get("/analyze/task-done")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == TaskStatus.COMPLETED
        assert data["result"]["fully_linked"] == 90
        assert data["result"]["partial"] == 3

    def test_미존재_task_에러_반환(self, test_client, mock_task_read_service):
        """존재하지 않는 task_id 조회 시 DataNotFoundError → 400 응답"""
        mock_task_read_service.get_task.side_effect = DataNotFoundError("데이터를 찾을 수 없습니다")

        resp = test_client.get("/analyze/non-existent-task")

        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "DATA_NOT_FOUND"
        assert "찾을 수 없" in body["detail"]


# === GET /rejections ===


class TestGetRejections:
    def test_returns_paginated_rejections(self, test_client, mock_rejection_read_service):
        rejections = [
            make_rejection(source_id="row-001", field="temperature"),
            make_rejection(source_id="row-002", field="recorded_at"),
        ]
        mock_rejection_read_service.search.return_value = (rejections, 2)

        resp = test_client.get(
            "/rejections",
            params={"stage": "selection", "reason": "invalid_format", "page": 1, "size": 20},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_elements"] == 2
        assert body["page"] == 1
        assert body["size"] == 20
        assert len(body["content"]) == 2

        first = body["content"][0]
        assert first["stage"] == Stage.SELECTION
        assert first["reason"] == RejectionReason.INVALID_FORMAT
        assert first["source_id"] == "row-001"
        assert first["field"] == "temperature"

    def test_returns_empty_page(self, test_client, mock_rejection_read_service):
        mock_rejection_read_service.search.return_value = ([], 0)

        resp = test_client.get("/rejections")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_elements"] == 0
        assert body["content"] == []
        assert body["first"] is True
        assert body["last"] is True


# === GET /data ===


class TestSearchData:
    def test_returns_paginated_search_results(self, test_client, mock_data_read_service):
        selection = make_selection(video_id=1)
        odd_tag = make_odd_tag(video_id=1)
        label = make_label(video_id=1)

        results = [SearchResult(selection=selection, odd_tag=odd_tag, labels=[label])]
        mock_data_read_service.search.return_value = (results, 1)

        resp = test_client.get("/data", params={"task_id": "test-task-001", "page": 1, "size": 20})

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_elements"] == 1

        item = body["content"][0]
        assert item["video_id"] == 1
        assert item["weather"] == "sunny"
        assert item["time_of_day"] == "day"
        assert len(item["labels"]) == 1
        assert item["labels"][0]["object_class"] == "car"

    def test_cursor_페이징_after_사용(self, test_client, mock_data_read_service):
        """GET /data?after=100&size=10 → 커서 기반 페이징, next_after 존재"""
        selection = make_selection(video_id=200)
        odd_tag = make_odd_tag(video_id=200)
        label = make_label(video_id=200)

        results = [SearchResult(selection=selection, odd_tag=odd_tag, labels=[label])]
        mock_data_read_service.search.return_value = (results, 1)

        resp = test_client.get("/data", params={"after": 100, "size": 10})

        assert resp.status_code == 200
        body = resp.json()
        # 커서 페이징 응답: next_after가 마지막 결과의 id
        assert body["next_after"] == 200
        assert body["size"] == 10
        # offset 페이징 필드는 기본값(None/0)
        assert body["page"] is None
        assert body["total_elements"] == 0

    def test_cursor_빈_결과(self, test_client, mock_data_read_service):
        """GET /data?after=999999&size=10 → 빈 결과일 때 next_after=None"""
        mock_data_read_service.search.return_value = ([], 0)

        resp = test_client.get("/data", params={"after": 999999, "size": 10})

        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == []
        assert body["next_after"] is None


# === 페이징 검증 ===


class TestPaginationValidation:
    def test_page_와_after_동시_사용_불가_data(self, test_client, mock_data_read_service):
        """GET /data?page=1&after=100 → page와 after 동시 사용 시 400 에러"""
        resp = test_client.get("/data", params={"page": 1, "after": 100})

        assert resp.status_code == 400
        body = resp.json()
        assert "page" in body["detail"] and "after" in body["detail"]

    def test_page_와_after_동시_사용_불가_rejections(self, test_client, mock_rejection_read_service):
        """GET /rejections?page=1&after=100 → page와 after 동시 사용 시 400 에러"""
        resp = test_client.get("/rejections", params={"page": 1, "after": 100})

        assert resp.status_code == 400
        body = resp.json()
        assert "page" in body["detail"] and "after" in body["detail"]
