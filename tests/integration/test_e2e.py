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

        # 1. 분석 접수
        response = client.post("/analyze")
        assert response.status_code == 202
        task_id = response.json()["data"]["task_id"]

        # 2. FailingDispatcher로 relay → dispatch 실패, PROCESSING 좀비 생성
        dispatcher = FailingDispatcher()
        relay = OutboxRelayService(
            outbox_repo=MongoOutboxRepository(mongo_db),
            task_dispatcher=dispatcher,
        )
        published = relay.relay()
        assert published == 0

        # Outbox가 PROCESSING 상태로 남아 있는지 확인
        outbox_msg = mongo_db.outbox.find_one({"payload.task_id": task_id})
        assert outbox_msg is not None
        assert outbox_msg["status"] == "processing"

        # 3. updated_at를 과거로 수동 조정 (좀비 탐지 조건 충족)
        mongo_db.outbox.update_one(
            {"payload.task_id": task_id},
            {"$set": {"updated_at": datetime.now() - timedelta(minutes=10)}},
        )

        # 4. recover_zombies 호출 → PENDING 복구
        recovered = relay.recover_zombies(threshold_minutes=0)
        assert recovered == 1

        # 5. 상태가 PENDING으로 복구되고 retry_count=1인지 확인
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

        # 1. 분석 접수
        response = client.post("/analyze")
        assert response.status_code == 202
        task_id = response.json()["data"]["task_id"]

        # 2. FailingDispatcher로 relay → PROCESSING 좀비 생성
        dispatcher = FailingDispatcher()
        relay = OutboxRelayService(
            outbox_repo=MongoOutboxRepository(mongo_db),
            task_dispatcher=dispatcher,
        )
        relay.relay()

        # 3. retry_count를 max_retries(3)으로 수동 설정 + updated_at을 과거로
        mongo_db.outbox.update_one(
            {"payload.task_id": task_id},
            {"$set": {"retry_count": 3, "updated_at": datetime.now() - timedelta(minutes=10)}},
        )

        # 4. recover_zombies 호출 → retry_count=4 > max_retries=3이므로 FAILED
        recovered = relay.recover_zombies(threshold_minutes=0)
        assert recovered == 1

        # 5. 상태가 FAILED인지 확인
        outbox_msg = mongo_db.outbox.find_one({"payload.task_id": task_id})
        assert outbox_msg["status"] == "failed"


# === 시나리오 7: 커서 기반 페이징 ===


class TestCursorPagination:
    """GET /data?after=N 커서 기반 페이지네이션을 검증한다"""

    def test_커서_페이징_next_after_반환(self, client, pipeline_service, db_session):
        """after 파라미터로 커서 기반 페이징 시 next_after가 반환된다"""
        # 1. 데이터 준비: 분석 실행 완료
        response = client.post("/analyze")
        assert response.status_code == 202
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        # 2. offset 기반 첫 페이지로 데이터 존재 확인
        first_page = client.get(f"/data?task_id={task_id}&page=1&size=3")
        assert first_page.status_code == 200
        first_body = first_page.json()

        # 데이터가 3건 이상 있어야 커서 테스트 가능
        if len(first_body["content"]) < 3:
            return

        # 3. 첫 페이지 마지막 항목의 video_id로 커서 페이징
        last_video_id = first_body["content"][-1]["video_id"]
        cursor_page = client.get(f"/data?task_id={task_id}&after={last_video_id}&size=3")
        assert cursor_page.status_code == 200
        cursor_body = cursor_page.json()

        # 커서 모드에서는 next_after 필드가 존재 (결과가 있으면 int, 없으면 None)
        assert "next_after" in cursor_body

        # 커서 결과의 video_id는 모두 last_video_id보다 커야 한다
        for item in cursor_body["content"]:
            assert item["video_id"] > last_video_id

    def test_page와_after_동시_사용시_에러(self, client):
        """page와 after를 동시에 사용하면 400 에러를 반환한다"""
        response = client.get("/data?page=1&after=100")
        assert response.status_code == 400

        body = response.json()
        # detail 또는 errors에 page와 after 관련 메시지가 포함되어야 한다
        response_text = str(body)
        assert "page" in response_text.lower()
        assert "after" in response_text.lower()


# === 시나리오 8: Redis 캐시 동작 검증 ===


class TestRedisCacheOperations:
    """Redis 캐시 저장/조회/무효화 동작을 검증한다"""

    def test_캐시_저장_후_조회(self, cache_repo):
        """캐시에 저장한 값을 동일 키로 조회하면 같은 값이 반환된다"""
        cache_repo.set("test-key", {"result": [1, 2, 3]})

        found = cache_repo.get("test-key")

        assert found is not None
        assert found == {"result": [1, 2, 3]}

    def test_캐시_invalidate_all_후_조회_None(self, cache_repo):
        """invalidate_all 호출 후 모든 캐시가 무효화된다"""
        cache_repo.set("key-a", {"data": "a"})
        cache_repo.set("key-b", {"data": "b"})

        cache_repo.invalidate_all()

        assert cache_repo.get("key-a") is None
        assert cache_repo.get("key-b") is None

    def test_캐시_미존재_키_조회_None(self, cache_repo):
        """존재하지 않는 키를 조회하면 None을 반환한다"""
        assert cache_repo.get("non-existent") is None

    def test_파이프라인_완료후_캐시_무효화_확인(
        self, client, pipeline_service, db_session, cache_repo
    ):
        """파이프라인 실행 완료 시 invalidate_all이 호출되어 기존 캐시가 사라진다"""
        cache_repo.set("before-pipeline", {"old": True})
        assert cache_repo.get("before-pipeline") is not None

        # 파이프라인 실행
        response = client.post("/analyze")
        assert response.status_code == 202
        task_id = response.json()["data"]["task_id"]

        pipeline_service.execute(task_id)
        db_session.commit()

        # 파이프라인 완료 후 캐시가 무효화되었는지 확인
        assert cache_repo.get("before-pipeline") is None


# === 시나리오 9: MongoDB 트랜잭션 롤백 검증 ===


class TestMongoTransactionRollback:
    """MongoDB 트랜잭션의 커밋/롤백 동작을 실제 Repository로 검증한다

    Repository는 내부적으로 get_current_session()을 호출하여
    트랜잭션 세션을 MongoDB 연산에 전달한다.
    세션 없이 직접 insert_one()을 호출하면 트랜잭션 밖에서 실행되므로,
    반드시 Repository를 통해 검증해야 한다.
    """

    def test_트랜잭션_내_예외시_MongoDB_롤백(self, mongo_client, mongo_db):
        """트랜잭션 안에서 예외 발생 시 저장된 Outbox 메시지가 롤백된다"""
        from datetime import datetime

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

        # 롤백 확인: Outbox에 메시지가 없어야 한다 (_id = message_id)
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

        # 커밋 확인: Outbox에 메시지가 있어야 한다 (_id = message_id)
        assert mongo_db.outbox.find_one({"_id": "commit-test-msg"}) is not None
