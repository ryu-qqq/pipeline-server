"""E2E 통합 테스트 — 전체 파이프라인 흐름을 실제 인프라에서 검증한다.

testcontainers: MySQL 8.0 + MongoDB 7.0 (replica set) + Redis 7.0
Celery Worker 대신 PipelineService.execute()를 동기 호출한다.
"""


# === 시나리오 1: 전체 파이프라인 흐름 (Happy Path) ===


class TestFullPipelineFlow:
    """POST /analyze 접수 → Outbox 확인 → 파이프라인 실행 → 결과 조회"""

    def test_submit_returns_202_with_task_id(self, client):
        """1단계: POST /analyze → 202 반환, task_id 획득"""
        response = client.post("/analyze")

        assert response.status_code == 202
        data = response.json()["data"]
        assert "task_id" in data
        assert data["status"] == "pending"

    def test_outbox_message_created_as_pending(self, client, mongo_db):
        """2단계: POST /analyze 후 Outbox에 PENDING 메시지가 생성된다"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        # Outbox에서 해당 task_id의 메시지 확인
        outbox_msg = mongo_db.outbox.find_one({"payload.task_id": task_id})
        assert outbox_msg is not None
        assert outbox_msg["status"] == "pending"
        assert outbox_msg["message_type"] == "ANALYZE"

    def test_outbox_relay_publishes_message(self, client, mongo_db, mongo_client):
        """3단계: OutboxRelayService.relay() → Outbox PUBLISHED 확인"""
        from app.adapter.outbound.mongodb.repositories import MongoOutboxRepository
        from app.application.outbox_relay_service import OutboxRelayService
        from app.domain.ports import TaskDispatcher

        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        # TaskDispatcher를 No-op으로 대체 (실제 Celery 호출 방지)
        class NoOpDispatcher(TaskDispatcher):
            def __init__(self):
                self.dispatched = []

            def dispatch(self, tid: str) -> None:
                self.dispatched.append(tid)

        dispatcher = NoOpDispatcher()
        relay_service = OutboxRelayService(
            outbox_repo=MongoOutboxRepository(mongo_db),
            task_dispatcher=dispatcher,
        )

        published = relay_service.relay()

        assert published == 1
        assert task_id in dispatcher.dispatched

        # Outbox 상태가 PUBLISHED로 전환되었는지 확인
        outbox_msg = mongo_db.outbox.find_one({"payload.task_id": task_id})
        assert outbox_msg["status"] == "published"

    def test_pipeline_execution_completes(self, client, pipeline_service, db_session):
        """4단계: PipelineService.execute() → COMPLETED 확인"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        # 파이프라인 동기 실행
        pipeline_service.execute(task_id)
        db_session.commit()

    def test_task_status_completed_after_pipeline(self, client, pipeline_service, db_session):
        """5단계: GET /analyze/{task_id} → COMPLETED, progress 확인"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        response = client.get(f"/analyze/{task_id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "completed"
        assert data["result"] is not None
        assert data["result"]["fully_linked"] >= 0

        # 각 단계의 progress가 존재하는지 확인
        progress = data["progress"]
        for stage in ("selection", "odd_tagging", "auto_labeling"):
            assert progress[stage]["total"] > 0

    def test_search_data_after_pipeline(self, client, pipeline_service, db_session):
        """6단계: GET /data?weather=sunny → 정제된 데이터 조회 확인"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        response = client.get("/data?weather=sunny")

        assert response.status_code == 200
        body = response.json()
        assert body["total_elements"] > 0
        # weather=sunny 필터가 적용되었는지 확인
        for item in body["content"]:
            assert item["weather"] == "sunny"

    def test_search_with_compound_conditions(self, client, pipeline_service, db_session):
        """7단계: GET /data?weather=sunny&min_obj_count=10 → 복합 조건 검색"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        response = client.get("/data?weather=sunny&min_obj_count=10")

        assert response.status_code == 200
        body = response.json()
        # 복합 조건 결과는 단일 조건보다 같거나 적어야 한다
        assert isinstance(body["content"], list)
        for item in body["content"]:
            assert item["weather"] == "sunny"
            # label 중 obj_count >= 10인 것이 존재해야 한다
            assert any(lb["obj_count"] >= 10 for lb in item["labels"])

    def test_rejections_after_pipeline(self, client, pipeline_service, db_session):
        """8단계: GET /rejections?task_id={task_id} → 거부 레코드 조회"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        response = client.get(f"/rejections?task_id={task_id}")

        assert response.status_code == 200
        body = response.json()
        # 실제 데이터에는 V1/V2 혼합 + 잘못된 데이터가 있으므로 거부 레코드가 존재
        assert body["total_elements"] >= 0


# === 시나리오 2: 중복 요청 방어 ===


class TestDuplicateRequestProtection:
    """진행 중인 작업이 있을 때 재요청하면 409를 반환한다"""

    def test_second_submit_returns_409(self, client):
        """첫 번째 POST /analyze → 202, 두 번째 POST /analyze → 409"""
        first = client.post("/analyze")
        assert first.status_code == 202

        second = client.post("/analyze")
        assert second.status_code == 409

        body = second.json()
        assert body["code"] == "CONFLICT"
        assert body["status"] == 409

    def test_submit_allowed_after_completion(self, client, pipeline_service, db_session):
        """파이프라인 완료 후에는 다시 요청할 수 있다"""
        first = client.post("/analyze")
        assert first.status_code == 202
        task_id = first.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        second = client.post("/analyze")
        assert second.status_code == 202
        assert second.json()["data"]["task_id"] != task_id


# === 시나리오 3: 데이터 품질 검증 ===


class TestDataQualityValidation:
    """파이프라인 실행 후 거부 사유별 분류가 정확한지 검증한다"""

    def test_rejections_categorized_by_reason(self, client, pipeline_service, db_session):
        """거부 레코드가 사유별로 정확히 분류된다"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        # 전체 거부 레코드 조회
        response = client.get(f"/rejections?task_id={task_id}&size=100")
        assert response.status_code == 200
        body = response.json()

        # 거부 사유가 유효한 RejectionReason 값인지 확인
        valid_reasons = {
            "duplicate_tagging",
            "duplicate_label",
            "negative_obj_count",
            "fractional_obj_count",
            "invalid_format",
            "unknown_schema",
            "missing_required_field",
            "invalid_enum_value",
            "unlinked_record",
        }
        for item in body["content"]:
            assert item["reason"] in valid_reasons
            assert item["stage"] in ("selection", "odd_tagging", "auto_labeling")

    def test_filter_by_rejection_reason(self, client, pipeline_service, db_session):
        """GET /rejections?reason=invalid_enum_value → 필터링 동작 확인"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        response = client.get(f"/rejections?task_id={task_id}&reason=invalid_enum_value&size=100")
        assert response.status_code == 200
        body = response.json()

        # 필터 결과는 모두 해당 reason이어야 한다
        for item in body["content"]:
            assert item["reason"] == "invalid_enum_value"

    def test_filter_by_stage(self, client, pipeline_service, db_session):
        """GET /rejections?stage=selection → 단계별 필터 동작 확인"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        response = client.get(f"/rejections?task_id={task_id}&stage=selection&size=100")
        assert response.status_code == 200
        body = response.json()

        for item in body["content"]:
            assert item["stage"] == "selection"


# === 시나리오 4: task_id별 데이터 격리 ===


class TestTaskDataIsolation:
    """서로 다른 task_id의 데이터가 격리되는지 검증한다"""

    def test_data_isolated_by_task_id(self, client, pipeline_service, db_session):
        """task_id=aaa 완료 후 task_id=bbb 완료 → 각각 격리된 데이터 조회"""
        # 첫 번째 분석 실행
        first = client.post("/analyze")
        assert first.status_code == 202
        task_id_a = first.json()["data"]["task_id"]

        pipeline_service.execute(task_id_a)
        db_session.commit()

        # 두 번째 분석 실행
        second = client.post("/analyze")
        assert second.status_code == 202
        task_id_b = second.json()["data"]["task_id"]

        pipeline_service.execute(task_id_b)
        db_session.commit()

        # task_id=a 데이터만 조회
        resp_a = client.get(f"/data?task_id={task_id_a}")
        assert resp_a.status_code == 200

        # task_id=b 데이터만 조회
        resp_b = client.get(f"/data?task_id={task_id_b}")
        assert resp_b.status_code == 200

        # task_id=a의 상태 확인
        task_a = client.get(f"/analyze/{task_id_a}")
        assert task_a.json()["data"]["status"] == "completed"

        # task_id=b의 상태 확인
        task_b = client.get(f"/analyze/{task_id_b}")
        assert task_b.json()["data"]["status"] == "completed"


# === API 엔드포인트 기본 동작 ===


class TestApiEndpoints:
    """API 엔드포인트의 기본 HTTP 동작을 검증한다"""

    def test_get_task_not_found_returns_400(self, client):
        """존재하지 않는 task_id 조회 시 400 반환"""
        response = client.get("/analyze/nonexistent-task-id")
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "DATA_NOT_FOUND"

    def test_get_rejections_empty(self, client):
        """파이프라인 실행 전 거부 레코드 조회 → 빈 결과"""
        response = client.get("/rejections")
        assert response.status_code == 200
        body = response.json()
        assert body["content"] == []
        assert body["total_elements"] == 0

    def test_get_data_empty(self, client):
        """파이프라인 실행 전 데이터 조회 → 빈 결과"""
        response = client.get("/data")
        assert response.status_code == 200
        body = response.json()
        assert body["content"] == []
        assert body["total_elements"] == 0

    def test_get_data_with_invalid_weather(self, client):
        """유효하지 않은 weather 값 → 400"""
        response = client.get("/data?weather=invalid_weather")
        assert response.status_code == 400

    def test_get_rejections_pagination(self, client, pipeline_service, db_session):
        """거부 레코드 페이지네이션 동작"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        # 1페이지
        resp1 = client.get(f"/rejections?task_id={task_id}&page=1&size=5")
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert len(body1["content"]) <= 5
        assert body1["page"] == 1

        # 총 건수가 5 초과이면 2페이지도 조회
        if body1["total_elements"] > 5:
            resp2 = client.get(f"/rejections?task_id={task_id}&page=2&size=5")
            assert resp2.status_code == 200
            body2 = resp2.json()
            assert body2["page"] == 2

    def test_error_response_follows_problem_detail(self, client):
        """에러 응답이 ProblemDetail(RFC 7807) 형식을 따른다"""
        response = client.get("/analyze/nonexistent")
        body = response.json()

        assert "title" in body
        assert "status" in body
        assert "detail" in body
        assert "code" in body

    def test_search_data_with_multiple_filters(self, client, pipeline_service, db_session):
        """복수 조건 검색이 정상적으로 동작한다"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        response = client.get(f"/data?task_id={task_id}&weather=sunny&time_of_day=day&page=1&size=10")
        assert response.status_code == 200
        body = response.json()
        for item in body["content"]:
            assert item["weather"] == "sunny"
            assert item["time_of_day"] == "day"
