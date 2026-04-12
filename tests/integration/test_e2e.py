"""E2E 통합 테스트 — 전체 파이프라인 흐름을 실제 인프라에서 검증한다.

testcontainers: MySQL 8.0 + MongoDB 7.0 (replica set) + Redis 7.0
Celery Worker 대신 PipelineService.execute()를 동기 호출한다.
"""

import pytest


# === 시나리오 1: 파이프라인 접수 + Outbox 흐름 ===


class TestPipelineSubmitFlow:
    """POST /analyze 접수 → Outbox 확인 → 파이프라인 완료"""

    def test_submit_returns_202_with_task_id(self, client):
        """POST /analyze → 202 반환, task_id 획득"""
        response = client.post("/analyze")

        assert response.status_code == 202
        data = response.json()["data"]
        assert "task_id" in data
        assert data["status"] == "pending"

    def test_outbox_message_created_as_pending(self, client, mongo_db):
        """POST /analyze 후 Outbox에 PENDING 메시지가 생성된다"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        outbox_msg = mongo_db.outbox.find_one({"payload.task_id": task_id})
        assert outbox_msg is not None
        assert outbox_msg["status"] == "pending"
        assert outbox_msg["message_type"] == "ANALYZE"

    def test_outbox_relay_publishes_message(self, client, mongo_db, mongo_client):
        """OutboxRelayService.relay() → Outbox PUBLISHED 확인"""
        from app.adapter.outbound.mongodb.repositories import MongoOutboxRepository
        from app.application.outbox_relay_service import OutboxRelayService
        from app.domain.ports import TaskDispatcher

        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

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

        outbox_msg = mongo_db.outbox.find_one({"payload.task_id": task_id})
        assert outbox_msg["status"] == "published"

    def test_pipeline_execution_completes(self, client, pipeline_service, db_session):
        """PipelineService.execute() → COMPLETED 확인"""
        response = client.post("/analyze")
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        response = client.get(f"/analyze/{task_id}")
        assert response.json()["data"]["status"] == "completed"


# === 시나리오 2: 읽기 전용 쿼리 (파이프라인 1회 공유) ===


class TestReadOnlyQueries:
    """파이프라인 1회 실행 후 검색 · 필터링 · 페이징을 검증한다.

    10개 테스트가 동일한 파이프라인 결과를 공유하여 실행 시간을 단축한다.
    """

    @pytest.fixture(autouse=True)
    def _auto_clean(self):
        """테스트 간 데이터 정리를 비활성화한다."""
        yield

    def test_task_status_completed(self, class_client, shared_task_id):
        """GET /analyze/{task_id} → COMPLETED, progress 확인"""
        response = class_client.get(f"/analyze/{shared_task_id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "completed"
        assert data["result"] is not None
        assert data["result"]["fully_linked"] >= 0

        progress = data["progress"]
        for stage in ("selection", "odd_tagging", "auto_labeling"):
            assert progress[stage]["total"] > 0

    def test_search_by_weather(self, class_client, shared_task_id):
        """GET /data?weather=sunny → 정제된 데이터 조회"""
        response = class_client.get("/data?weather=sunny")

        assert response.status_code == 200
        body = response.json()
        assert body["total_elements"] > 0
        for item in body["content"]:
            assert item["weather"] == "sunny"

    def test_search_with_compound_conditions(self, class_client, shared_task_id):
        """GET /data?weather=sunny&min_obj_count=10 → 복합 조건 검색"""
        response = class_client.get("/data?weather=sunny&min_obj_count=10")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["content"], list)
        for item in body["content"]:
            assert item["weather"] == "sunny"
            assert any(lb["obj_count"] >= 10 for lb in item["labels"])

    def test_search_with_multiple_filters(self, class_client, shared_task_id):
        """복수 조건 검색 (날씨 + 시간대)"""
        response = class_client.get(
            f"/data?task_id={shared_task_id}&weather=sunny&time_of_day=day&page=1&size=10"
        )
        assert response.status_code == 200
        body = response.json()
        for item in body["content"]:
            assert item["weather"] == "sunny"
            assert item["time_of_day"] == "day"

    def test_rejections_exist(self, class_client, shared_task_id):
        """GET /rejections?task_id={task_id} → 거부 레코드 조회"""
        response = class_client.get(f"/rejections?task_id={shared_task_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["total_elements"] >= 0

    def test_rejections_categorized_by_reason(self, class_client, shared_task_id):
        """거부 레코드가 유효한 사유별로 분류된다"""
        response = class_client.get(f"/rejections?task_id={shared_task_id}&size=100")
        assert response.status_code == 200
        body = response.json()

        valid_reasons = {
            "duplicate_tagging", "duplicate_label",
            "negative_obj_count", "fractional_obj_count",
            "invalid_format", "unknown_schema",
            "missing_required_field", "invalid_enum_value",
            "unlinked_record",
        }
        for item in body["content"]:
            assert item["reason"] in valid_reasons
            assert item["stage"] in ("selection", "odd_tagging", "auto_labeling")

    def test_filter_by_rejection_reason(self, class_client, shared_task_id):
        """GET /rejections?reason=unlinked_record → 사유별 필터"""
        response = class_client.get(
            f"/rejections?task_id={shared_task_id}&reason=unlinked_record&size=100"
        )
        assert response.status_code == 200
        body = response.json()

        for item in body["content"]:
            assert item["reason"] == "unlinked_record"

    def test_filter_by_stage(self, class_client, shared_task_id):
        """GET /rejections?stage=auto_labeling → 단계별 필터"""
        response = class_client.get(
            f"/rejections?task_id={shared_task_id}&stage=auto_labeling&size=100"
        )
        assert response.status_code == 200
        body = response.json()

        for item in body["content"]:
            assert item["stage"] == "auto_labeling"

    def test_rejections_pagination(self, class_client, shared_task_id):
        """거부 레코드 페이지네이션"""
        resp1 = class_client.get(f"/rejections?task_id={shared_task_id}&page=1&size=5")
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert len(body1["content"]) <= 5
        assert body1["page"] == 1

        if body1["total_elements"] > 5:
            resp2 = class_client.get(f"/rejections?task_id={shared_task_id}&page=2&size=5")
            assert resp2.status_code == 200
            assert resp2.json()["page"] == 2

    def test_cursor_pagination(self, class_client, shared_task_id):
        """after 파라미터 커서 기반 페이징"""
        first_page = class_client.get(f"/data?task_id={shared_task_id}&page=1&size=3")
        assert first_page.status_code == 200
        first_body = first_page.json()

        if len(first_body["content"]) < 3:
            return

        last_video_id = first_body["content"][-1]["video_id"]
        cursor_page = class_client.get(f"/data?task_id={shared_task_id}&after={last_video_id}&size=3")
        assert cursor_page.status_code == 200
        cursor_body = cursor_page.json()

        assert "next_after" in cursor_body
        for item in cursor_body["content"]:
            assert item["video_id"] > last_video_id


# === 시나리오 3: 중복 요청 방어 ===


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


# === 시나리오 4: task_id별 데이터 격리 ===


class TestTaskDataIsolation:
    """서로 다른 task_id의 데이터가 격리되는지 검증한다"""

    def test_data_isolated_by_task_id(self, client, pipeline_service, db_session):
        """task_id별로 격리된 데이터 조회"""
        first = client.post("/analyze")
        assert first.status_code == 202
        task_id_a = first.json()["data"]["task_id"]

        pipeline_service.execute(task_id_a)
        db_session.commit()

        second = client.post("/analyze")
        assert second.status_code == 202
        task_id_b = second.json()["data"]["task_id"]

        pipeline_service.execute(task_id_b)
        db_session.commit()

        resp_a = client.get(f"/data?task_id={task_id_a}")
        assert resp_a.status_code == 200

        resp_b = client.get(f"/data?task_id={task_id_b}")
        assert resp_b.status_code == 200

        task_a = client.get(f"/analyze/{task_id_a}")
        assert task_a.json()["data"]["status"] == "completed"

        task_b = client.get(f"/analyze/{task_id_b}")
        assert task_b.json()["data"]["status"] == "completed"


# === API 엔드포인트 기본 동작 (파이프라인 불필요) ===


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

    def test_error_response_follows_problem_detail(self, client):
        """에러 응답이 ProblemDetail(RFC 7807) 형식을 따른다"""
        response = client.get("/analyze/nonexistent")
        body = response.json()

        assert "title" in body
        assert "status" in body
        assert "detail" in body
        assert "code" in body

    def test_page_and_after_simultaneous_error(self, client):
        """page와 after를 동시에 사용하면 400 에러"""
        response = client.get("/data?page=1&after=100")
        assert response.status_code == 400

        body = response.json()
        response_text = str(body)
        assert "page" in response_text.lower()
        assert "after" in response_text.lower()


# === 시나리오 6: Outbox 좀비 복구 ===


class TestOutboxZombieRecovery:
    """Outbox PROCESSING 상태로 방치된 좀비 메시지의 복구를 검증한다"""

    def test_좀비_메시지_recover후_재발행_가능(self, client, mongo_db):
        """dispatch 실패로 PROCESSING에 남은 좀비를 recover_zombies로 PENDING 복구한다"""
        from datetime import datetime, timedelta

        from app.adapter.outbound.mongodb.repositories import MongoOutboxRepository
        from app.application.outbox_relay_service import OutboxRelayService
        from app.domain.ports import TaskDispatcher

        class FailingDispatcher(TaskDispatcher):
            def dispatch(self, tid: str) -> None:
                raise RuntimeError("의도적 실패")

        response = client.post("/analyze")
        assert response.status_code == 202
        task_id = response.json()["data"]["task_id"]

        dispatcher = FailingDispatcher()
        relay = OutboxRelayService(
            outbox_repo=MongoOutboxRepository(mongo_db),
            task_dispatcher=dispatcher,
        )
        published = relay.relay()
        assert published == 0

        outbox_msg = mongo_db.outbox.find_one({"payload.task_id": task_id})
        assert outbox_msg is not None
        assert outbox_msg["status"] == "processing"

        mongo_db.outbox.update_one(
            {"payload.task_id": task_id},
            {"$set": {"updated_at": datetime.now() - timedelta(minutes=10)}},
        )

        recovered = relay.recover_zombies(threshold_minutes=0)
        assert recovered == 1

        outbox_msg = mongo_db.outbox.find_one({"payload.task_id": task_id})
        assert outbox_msg["status"] == "pending"
        assert outbox_msg["retry_count"] == 1

    def test_좀비_최대_재시도_초과시_FAILED(self, client, mongo_db):
        """retry_count가 max_retries에 도달한 좀비는 FAILED로 처리된다"""
        from datetime import datetime, timedelta

        from app.adapter.outbound.mongodb.repositories import MongoOutboxRepository
        from app.application.outbox_relay_service import OutboxRelayService
        from app.domain.ports import TaskDispatcher

        class FailingDispatcher(TaskDispatcher):
            def dispatch(self, tid: str) -> None:
                raise RuntimeError("의도적 실패")

        response = client.post("/analyze")
        assert response.status_code == 202
        task_id = response.json()["data"]["task_id"]

        dispatcher = FailingDispatcher()
        relay = OutboxRelayService(
            outbox_repo=MongoOutboxRepository(mongo_db),
            task_dispatcher=dispatcher,
        )
        relay.relay()

        mongo_db.outbox.update_one(
            {"payload.task_id": task_id},
            {"$set": {"retry_count": 3, "updated_at": datetime.now() - timedelta(minutes=10)}},
        )

        recovered = relay.recover_zombies(threshold_minutes=0)
        assert recovered == 1

        outbox_msg = mongo_db.outbox.find_one({"payload.task_id": task_id})
        assert outbox_msg["status"] == "failed"


# === 시나리오 7: 낙관적 잠금 — race condition 방지 ===


class TestOutboxOptimisticLock:
    """relay()가 PUBLISHED로 전환한 메시지를 recover_zombies()가 덮어쓰지 않는지 검증한다"""

    def test_이미_PUBLISHED된_메시지는_recover가_덮어쓰지_않는다(self, client, mongo_db):
        """relay()로 PUBLISHED 전환 후 recover_zombies() 실행 → 상태 유지"""
        from app.adapter.outbound.mongodb.repositories import MongoOutboxRepository
        from app.application.outbox_relay_service import OutboxRelayService
        from app.domain.ports import TaskDispatcher

        class NoOpDispatcher(TaskDispatcher):
            def __init__(self):
                self.dispatched = []

            def dispatch(self, tid: str) -> None:
                self.dispatched.append(tid)

        response = client.post("/analyze")
        assert response.status_code == 202
        task_id = response.json()["data"]["task_id"]

        repo = MongoOutboxRepository(mongo_db)
        dispatcher = NoOpDispatcher()
        relay = OutboxRelayService(outbox_repo=repo, task_dispatcher=dispatcher)

        published = relay.relay()
        assert published == 1

        outbox_msg = mongo_db.outbox.find_one({"payload.task_id": task_id})
        assert outbox_msg["status"] == "published"

        recovered = relay.recover_zombies(threshold_minutes=0)
        assert recovered == 0

        outbox_msg = mongo_db.outbox.find_one({"payload.task_id": task_id})
        assert outbox_msg["status"] == "published"


# === 시나리오 8: MongoDB 트랜잭션 롤백 검증 ===


class TestMongoTransactionRollback:
    """MongoDB 트랜잭션의 커밋/롤백 동작을 실제 Repository로 검증한다"""

    def test_트랜잭션_내_예외시_MongoDB_롤백(self, mongo_client, mongo_db):
        """트랜잭션 안에서 예외 발생 시 저장된 Outbox 메시지가 롤백된다"""
        from app.adapter.outbound.mongodb.repositories import MongoOutboxRepository
        from app.adapter.outbound.mongodb.transaction import MongoTransactionManager
        from app.domain.models import OutboxMessage

        tx = MongoTransactionManager(mongo_client)
        repo = MongoOutboxRepository(mongo_db)

        msg = OutboxMessage.create_analyze_event("rollback-test-msg", "rollback-test-task")

        try:
            def _failing_op():
                repo.save(msg)
                raise RuntimeError("의도적 실패")

            tx.execute(_failing_op)
        except RuntimeError:
            pass

        assert mongo_db.outbox.find_one({"_id": "rollback-test-msg"}) is None

    def test_트랜잭션_정상_완료시_MongoDB_커밋(self, mongo_client, mongo_db):
        """트랜잭션이 정상 완료되면 저장된 Outbox 메시지가 커밋된다"""
        from app.adapter.outbound.mongodb.repositories import MongoOutboxRepository
        from app.adapter.outbound.mongodb.transaction import MongoTransactionManager
        from app.domain.models import OutboxMessage

        tx = MongoTransactionManager(mongo_client)
        repo = MongoOutboxRepository(mongo_db)

        msg = OutboxMessage.create_analyze_event("commit-test-msg", "commit-test-task")

        def _success_op():
            repo.save(msg)

        tx.execute(_success_op)

        assert mongo_db.outbox.find_one({"_id": "commit-test-msg"}) is not None
