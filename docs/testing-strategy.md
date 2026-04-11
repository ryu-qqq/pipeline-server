# 테스트 전략 — pipeline-server

## 1. 테스트 피라미드 개요

```
         ╱  E2E (21)  ╲          ← Testcontainers (MySQL + MongoDB + Redis)
        ╱───────────────╲         ~12분, Docker 필요
       ╱  Adapter (56)   ╲       ← MySQL Testcontainer + TestClient Mock
      ╱───────────────────╲       ~7초
     ╱  Application (107)  ╲     ← MagicMock(spec=ABC)
    ╱───────────────────────╲     ~0.08초
   ╱     Domain (95)         ╲   ← 순수 Python, 외부 의존 없음
  ╱───────────────────────────╲   ~0.03초
```

| 레이어 | 테스트 수 | 비율 | 실행 시간 | DB |
|--------|:--------:|:----:|:---------:|-----|
| Domain | 95 | 34% | 0.03s | 없음 |
| Application | 107 | 38% | 0.08s | Mock |
| Adapter | 56 | 20% | ~7s | MySQL Testcontainer |
| Integration (E2E) | 21 | 8% | ~13m | MySQL + MongoDB + Redis Testcontainer |
| **합계** | **279** | 100% | | |

단위 테스트(Domain + Application)만 실행하면 **0.1초**, Adapter 포함 시 **7초**, E2E 포함 시 **~14분**.

---

## 2. Domain 테스트

**위치**: `tests/domain/`  
**대상**: `app/domain/models.py`, `app/domain/value_objects.py`  
**원칙**: 순수 Python만. Mock 없음, DB 없음, 외부 의존 없음.

### test_value_objects.py — 46개

값 객체(VO)가 스스로 유효성을 보장하는지 검증한다.

| 대상 | 시나리오 |
|------|---------|
| VideoId | 양수만 허용, 0과 음수 거부, int 동등성 비교, 해시 일관성 |
| Temperature | 섭씨 -90~60도 범위 검증, 범위 초과 시 에러 발생, `from_celsius` 소수점 반올림, `from_fahrenheit` 화씨→섭씨 변환 정확성 (32°F=0°C, 100°F≈37.78°C), 변환 결과가 범위 밖이면 에러, **NaN/Infinity/음의 무한대 거부, 화씨 입력의 NaN/Infinity 거부** |
| Confidence | 0.0~1.0 범위 검증, 범위 밖 값 거부, `is_high` 기본/커스텀 임계값 판단, `is_low` 기본/커스텀 임계값 판단, **NaN/Infinity 거부** |
| ObjectCount | 0 이상 정수만 허용, 음수 거부 시 전용 예외(NegativeCountError), `is_empty` 판단, 크기 비교 연산 |
| WiperState | 와이퍼 레벨 0~3 범위 검증, 비활성 상태에서 레벨 양수 거부, `is_raining_likely` 판단 (활성+레벨2 이상), 다양한 조합(활성/비활성 × 레벨 있음/없음) |
| SourcePath | 빈 문자열 거부, .mp4 이외 확장자 거부, `/raw/` 경로와 `/processed/` 경로 구분 |
| StageProgress | 진행률 계산 `(처리+거부)/전체×100`, 전체가 0일 때 0.0 반환 (나눗셈 오류 방지), 기본값 확인 |

### test_models.py — 49개

도메인 모델의 비즈니스 규칙과 상태 전이가 올바른지 검증한다.

| 대상 | 시나리오 |
|------|---------|
| Selection | frozen 불변성 (필드 변경 시 에러), 헤드라이트 켜짐으로 야간 주행 판단, 와이퍼 레벨 또는 영하 온도로 악천후 판단 |
| OddTag | id가 0이거나 음수이면 생성 실패, 빙판/적설 노면 또는 폭설일 때 위험 환경 판단, 야간 또는 비/눈일 때 저시정 판단 |
| Label | 신뢰도 기반 신뢰성 판단 (기본 0.8, 커스텀 임계값), 탐지 객체 존재 여부 판단 |
| Rejection | `source_id`와 `detail`이 빈 문자열이면 생성 실패 |
| AnalyzeTask | `create_new` 팩토리로 PENDING 상태 생성, PENDING→PROCESSING→COMPLETED 전이 체인 (원본 불변 확인), PENDING→PROCESSING→FAILED 전이 체인 (에러 메시지 포함), `should_run_phase` resume 로직 — 완료된 단계 이후만 실행 (SELECTION 완료→ODD/LABEL만, ODD 완료→LABEL만), 단계별 진행률 갱신과 완료 Phase 기록 |
| OutboxMessage | `create_analyze_event` 팩토리로 PENDING 메시지 생성, PENDING→PROCESSING→PUBLISHED 상태 전이, 발행 실패 시 PENDING으로 되돌리기 (좀비 복구), 재시도 횟수 증가와 최대 재시도(3회) 도달 시 `is_retriable=False` 전환, 전체 재시도 체인 (0→1→2→3회 순차 검증) |
| AnalysisResult | frozen 불변성, 각 단계 결과 값 접근 |

### 실행

```bash
pytest tests/domain/ -v    # 95개, ~0.03초
```

---

## 3. Application 테스트

**위치**: `tests/application/`  
**대상**: `app/application/*.py`  
**원칙**: `MagicMock(spec=ABC포트)` 기반 단위 테스트. 구체 구현체 Mock 금지.

### Mock 전략

```python
# Port(ABC) 인터페이스 기준 Mock — 도메인이 정의한 계약만 검증
mock_task_repo = MagicMock(spec=TaskRepository)
mock_outbox_repo = MagicMock(spec=OutboxRepository)
```

### test_phase_runners.py — 31개

정제 파이프라인의 핵심 엔진인 PhaseRunner의 스트리밍 처리, 중복 탐지, 미참조 영상 거부, 진행률 추적을 검증한다.

| 대상 | 시나리오 |
|------|---------|
| PhaseRunnerProvider | 등록된 Stage로 올바른 runner 반환, 미등록 Stage 조회 시 ValueError, 여러 Stage 동시 등록 |
| Runner 속성 | Selection/OddTag/Label runner 각각의 stage와 source 값 확인 |
| run() 흐름 | 정상 스트리밍 데이터 처리 (정제→적재→결과 반환), 빈 데이터 입력 시 0건 처리, 모든 row 정제 실패 시 rejected_count만 증가, 일부 성공+일부 실패 혼합 처리, 청크 크기 초과 시 분할 처리 |
| INSERT IGNORE 중복 | 중복 0건이면 duplicate rejection 미생성, 부분 중복 시 무시된 건수만큼 rejection 생성, 전체 중복 시 inserted=0 |
| 중복 rejection 분류 | ODD_TAGGING Stage → DUPLICATE_TAGGING 사유, AUTO_LABELING Stage → DUPLICATE_LABEL 사유 |
| _refine_chunk 분기 | 반환이 list[Rejection]이면 extend, 단일 Rejection이면 append, 도메인 모델이면 valid에 추가, 혼합 결과 올바른 분리 |
| 진행률 갱신 | run() 완료 후 with_progress와 with_completed_phase 호출, task_repo.save 호출, 실패 포함 진행률 정확성 |
| **UNLINKED_RECORD 거부** | **OddTag Phase에서 Selection에 없는 video_id → UNLINKED_RECORD 거부, Label Phase에서 동일, 모든 video_id가 유효하면 UNLINKED 거부 0건** |

### test_selection_refiner.py — 17개

V1(평면)/V2(중첩 sensor) 두 스키마를 자동 감지하여 Selection 모델로 정제하는 로직을 검증한다.

| 대상 | 시나리오 |
|------|---------|
| V1 스키마 | 정상 파싱, id 누락 시 rejection, temperature 누락 시 unknown schema, 잘못된 온도 값, 와이퍼 누락, 헤드라이트 누락, 잘못된 파일 확장자, 3개 이상 필드 동시 에러 시 모든 rejection 수집 |
| V2 스키마 | 화씨→섭씨 변환 정상 파싱, 섭씨 단위 정상 파싱, sensor 필드가 dict가 아닌 경우 rejection, 알 수 없는 온도 단위(K) rejection, 와이퍼 누락 시 rejection, 다중 에러 수집 |
| 스키마 감지 | sensor도 temperature도 없는 dict → UNKNOWN_SCHEMA rejection, 완전히 빈 dict `{}` 입력 |

### test_odd_tag_refiner.py — 11개

ODD 태깅 원본 데이터를 도메인 모델로 정제하는 로직을 검증한다.

| 대상 | 시나리오 |
|------|---------|
| 정상 파싱 | weather/time_of_day/road_surface를 enum으로 변환, video_id 앞의 0 제거 ("0042"→42) |
| 필드 누락 | weather/time_of_day/road_surface 각각 누락 시 MISSING_REQUIRED_FIELD rejection |
| 잘못된 enum 값 | "tornado", "dusk", "gravel" 등 유효하지 않은 값 → INVALID_ENUM_VALUE rejection |
| 다중 에러 | 3개 필드 모두 에러 시 3건 rejection 반환, 누락과 잘못된 값 혼합, 빈 dict `{}` 시 최소 3건 이상 |

### test_label_refiner.py — 11개

자동 라벨링 데이터를 도메인 모델로 정제하는 로직을 검증한다.

| 대상 | 시나리오 |
|------|---------|
| 정상 파싱 | video_id, object_class enum, obj_count, confidence 변환, obj_count=0 허용 |
| 소수점 obj_count | 3.5 → FRACTIONAL_OBJ_COUNT rejection, 5.0(정수와 동일한 실수) → 정상 허용 |
| 음수 obj_count | -1 → NEGATIVE_OBJ_COUNT rejection |
| 필드 누락 | object_class 누락, avg_confidence 누락, 잘못된 object_class enum 값 |
| 다중 에러 | obj_count + object_class + confidence 동시 에러, video_id와 obj_count 동시 에러, 빈 dict `{}` 시 4건 이상 |

### test_outbox_relay_service.py — 9개

Outbox 메시지 발행과 좀비 복구 흐름을 검증한다.

| 대상 | 시나리오 |
|------|---------|
| relay() | 정상 흐름 — PENDING 조회→PROCESSING 전환→dispatch→PUBLISHED (순서 검증), 여러 건 처리, PENDING 없으면 0 반환, 발행 실패 시 PROCESSING 상태 유지, 부분 실패 시 성공 건수만 반환 |
| recover_zombies() | 재시도 가능하면 PENDING으로 복구, 재시도 횟수 초과 시 FAILED, 좀비 없으면 0 반환, 여러 좀비 개별 처리 |

### test_pipeline_service.py — 6개

정제 파이프라인 오케스트레이터의 Phase 순서 제어와 완료/실패 관리를 검증한다.

| 대상 | 시나리오 |
|------|---------|
| 전체 흐름 | SELECTION→ODD_TAGGING→AUTO_LABELING 3단계 순차 실행, start_processing 저장 후 complete_with 저장 |
| 실패 처리 | runner에서 예외 발생 시 fail_with 호출, 에러 메시지 포함, FAILED 상태 저장 |
| resume 로직 | SELECTION 완료 시 ODD_TAGGING+AUTO_LABELING만 실행, ODD_TAGGING 완료 시 AUTO_LABELING만 실행, 스킵된 Phase는 기존 progress에서 StageResult 생성 |
| fully_linked 계산 | Selection∩OddTag∩Label 교집합이 0인 경우 (fully_linked=0, partial=전체), 전체 일치하는 경우 (fully_linked=전체, partial=0) |

### test_analysis_service.py — 4개

분석 요청 접수(적재→Task/Outbox 생성) 흐름을 검증한다.

| 대상 | 시나리오 |
|------|---------|
| submit() | 정상 흐름 — ingest 호출 후 `create_if_not_active`로 원자적 Task 생성 + Outbox 저장, **활성 작업 존재 시 `create_if_not_active`가 ConflictError 발생**, ConflictError 시 outbox 저장 미호출, 트랜잭션 매니저 execute 호출 확인 |

### test_read_services.py — 6개

조회 서비스(Query)의 위임과 에러 처리를 검증한다.

| 대상 | 시나리오 |
|------|---------|
| TaskReadService | task_id로 조회 시 정상 반환, 존재하지 않는 task_id 조회 시 DataNotFoundError |
| DataReadService | 검색 조건 전달 시 Repository에 위임 확인, 빈 결과 반환 |
| RejectionReadService | 검색 조건 전달 시 Repository에 위임 확인, 빈 결과 반환 |

### test_file_loaders.py — 12개

파일 로더의 JSON/CSV 파싱과 엣지 케이스를 검증한다.

| 대상 | 시나리오 |
|------|---------|
| JsonFileLoader | 정상 JSON 배열 파싱 (ijson 스트리밍), 빈 배열 반환, 존재하지 않는 파일 시 DataNotFoundError, 깨진 JSON 시 InvalidFormatError, JSON이 배열이 아닌 dict인 경우 빈 결과 반환 (ijson 스트리밍 특성) |
| CsvFileLoader | 정상 CSV 파싱 (DictReader로 문자열 반환), 헤더만 있는 CSV → 빈 리스트, 존재하지 않는 파일 시 DataNotFoundError |
| FileLoaderProvider | 등록된 FileType으로 올바른 로더 반환, 미등록 타입 시 InvalidFormatError, 파일 확장자에서 로더 자동 감지 (.json→JsonFileLoader, .csv→CsvFileLoader), 지원하지 않는 확장자(.xml) 시 InvalidFormatError |

### 실행

```bash
pytest tests/application/ -v    # 107개, ~0.08초
```

---

## 4. Adapter 테스트

**위치**: `tests/adapter/`  
**대상**: `app/adapter/**/*.py`  
**원칙**: MySQL Testcontainer로 실제 SQL 실행. Router는 Mock 서비스 + TestClient.

### test_mysql_repositories.py — 18개

실제 MySQL에서 Repository의 저장/조회/검색이 올바르게 동작하는지 검증한다.

| 대상 | 시나리오 |
|------|---------|
| SelectionRepository | `save_all` 후 `find_by_id`로 조회, 존재하지 않는 id 조회 시 None, task_id로 전체 id 집합 조회 (다른 task 제외), **동일 video_id 중복 저장 시 INSERT IGNORE로 0건 반환** |
| OddTagRepository | `save_all` 후 `find_by_video_id`로 조회, 존재하지 않는 video_id 조회 시 None, task_id로 전체 video_id 집합 조회, **동일 video_id 중복 저장 시 INSERT IGNORE로 0건 반환** |
| LabelRepository | `save_all` 후 같은 video_id의 여러 Label 조회, task_id로 전체 video_id 집합 조회 (distinct) |
| RejectionRepository | 저장 후 task_id로 검색, stage별 필터링, reason별 필터링, source_id+field 복합 필터, 페이지네이션 (사이즈 2로 5건 분할), 빈 결과 |
| DataSearchRepository | Selection+OddTag+Label 통합 조합 결과 반환, 빈 결과 |

### test_query_builder.py — 16개

QueryBuilder가 MySQL 방언으로 올바른 SQL을 생성하는지 검증한다.

| 대상 | 시나리오 |
|------|---------|
| DataSearchQueryBuilder | task_id 필터, recorded_at 날짜 범위, temperature 온도 범위, headlights_on 불린 필터, weather/time_of_day/road_surface 조건 시 ODD_TAGS JOIN, object_class/obj_count/confidence 조건 시 EXISTS 서브쿼리, LIMIT offset/count 페이지네이션, COUNT 쿼리에서 LIMIT 제거, 조건 없을 때 기본 조회 |
| RejectionQueryBuilder | task_id/stage/reason/source_id/field 각각 단독 필터, 5개 조건 복합 필터, LIMIT 페이지네이션, COUNT 쿼리 |

### test_mappers.py — 9개

도메인 모델 ↔ DB 엔티티, REST 요청 ↔ 도메인 모델 간 매핑 정확성을 검증한다.

| 대상 | 시나리오 |
|------|---------|
| SelectionMapper | 도메인→엔티티→도메인 왕복 변환 후 동등성, to_dict 결과가 엔티티 필드와 일치 |
| OddTagMapper | 왕복 변환 동등성 |
| LabelMapper | 왕복 변환 동등성 |
| RejectionMapper | 왕복 변환 동등성 |
| RejectionCriteriaMapper | REST 요청(전체 필드) → 도메인 Criteria 변환, REST 요청(최소 필드) → 기본값 적용 |
| DataSearchCriteriaMapper | REST 요청(전체 필드) → 도메인 Criteria 변환, REST 요청(최소 필드) → 기본값 적용 |

### test_routers.py — 13개

REST API의 HTTP 응답과 에러 핸들링을 검증한다.

| 대상 | 시나리오 |
|------|---------|
| POST /analyze | 정상 접수 시 202 반환 + task_id와 PENDING 상태 포함, **진행 중인 작업 존재 시 409 반환** |
| GET /analyze/{task_id} | 진행 중인 Task의 progress 필드 (selection/odd_tagging/auto_labeling 각각 total/processed/rejected/percent), 완료된 Task의 result 필드 (fully_linked, partial), **존재하지 않는 task_id 조회 시 에러 응답** |
| GET /rejections | 필터 적용된 페이지네이션 응답 (total_elements, page, size, content), 빈 결과 시 first=true, last=true |
| GET /data | offset 기반 페이지네이션 응답 (video_id별 selection+odd_tag+labels 조합), **cursor 기반 페이징 (after 파라미터) 시 next_after 반환**, **after 파라미터로 빈 결과 시 next_after=None**, **page와 after 동시 사용 시 400 에러** (data, rejections 각각) |

### 실행

```bash
pytest tests/adapter/ -v    # 56개, ~7초 (컨테이너 기동 포함)
```

---

## 5. 통합 테스트 (E2E)

**위치**: `tests/integration/`  
**대상**: 전체 앱 (REST → Service → Repository → DB)  
**원칙**: Testcontainers로 실제 인프라 사용. Celery 대신 동기 호출.

### 인프라 구성

```
┌──────────────────────────────────────────────┐
│              Testcontainers                   │
│                                              │
│  MySQL 8.0     MongoDB 7.0     Redis 7.0     │
│  (selections,  (raw_data,      (Celery       │
│   odd_tags,    analyze_tasks,                │
│   labels,      outbox)         브로커)        │
│   rejections)                                │
└──────────────────────────────────────────────┘

대체:
  Celery Worker  → PipelineService.execute() 동기 호출
  TaskDispatcher → NoOpDispatcher (dispatched 리스트 추적)
```

### MongoDB 안정성 설정

```python
# MongoClient 연결 복원력
MongoClient(
    url,
    serverSelectionTimeoutMS=60000,
    socketTimeoutMS=60000,
    connectTimeoutMS=30000,
    retryWrites=True,
    retryReads=True,
)

# teardown 내결함성 — cascade 실패 방지
@pytest.fixture()
def _clean_mongo(mongo_db):
    yield
    for coll_name in ("raw_data", "analyze_tasks", "outbox"):
        try:
            mongo_db[coll_name].delete_many({})
        except Exception:
            pass
```

**TESTCONTAINERS_RYUK_DISABLED=true** 환경변수를 설정하여 Ryuk이 컨테이너를 조기 정리하는 문제를 방지한다.

### test_e2e.py — 21개

실제 인프라에서 전체 파이프라인 흐름이 올바르게 동작하는지 검증한다.

| 테스트 클래스 | 시나리오 |
|-------------|---------|
| **TestFullPipelineFlow** (8개) | POST /analyze 접수 시 202 + task_id 반환, 접수 후 MongoDB Outbox에 PENDING 메시지 생성 확인, OutboxRelayService.relay()로 메시지 PUBLISHED 전환, PipelineService.execute()로 파이프라인 완료, GET /analyze/{task_id}에서 COMPLETED 상태 + 각 단계 progress 확인, GET /data?weather=sunny로 정제된 데이터 조회 (필터 정확성), GET /data?weather=sunny&min_obj_count=10 복합 조건 검색, GET /rejections?task_id={id}로 거부 레코드 조회 |
| **TestDuplicateRequestProtection** (2개) | 진행 중인 작업이 있을 때 두 번째 POST /analyze → 409 반환 (CONFLICT), 파이프라인 완료 후에는 새 task_id로 재요청 가능 (202) |
| **TestDataQualityValidation** (3개) | 파이프라인 실행 후 모든 거부 사유가 유효한 RejectionReason 값인지 확인, GET /rejections?reason=invalid_enum_value 필터링 동작, GET /rejections?stage=selection 단계별 필터 동작 |
| **TestTaskDataIsolation** (1개) | 두 번의 독립적인 분석 실행 후 각 task_id별 데이터가 격리되는지 확인 (교차 조회 없음) |
| **TestApiEndpoints** (7개) | 존재하지 않는 task_id → 400 (DATA_NOT_FOUND), 파이프라인 실행 전 빈 rejections/data 조회, 유효하지 않은 enum 값 → 400, 페이지네이션 동작 (page=1, size=5 → page=2), ProblemDetail(RFC 7807) 형식 검증 (title, status, detail, code), 복수 조건 검색 (weather+time_of_day 동시 필터) |
| **TestOutboxZombieRecovery** (2개) | dispatch 실패로 PROCESSING에 남은 좀비 메시지를 recover_zombies()로 PENDING 복구 + retry_count 증가 확인, 재시도 횟수가 max_retries(3)를 초과한 좀비는 FAILED로 최종 처리 |
| **TestCursorPagination** (2개) | offset 기반 첫 페이지 조회 후 마지막 video_id로 cursor 페이징 → next_after 반환 + 결과 video_id가 모두 커서보다 큼, page와 after를 동시에 전달하면 400 에러 + 에러 메시지에 "page"와 "after" 포함 |
| **TestMongoTransactionRollback** (2개) | 트랜잭션 안에서 Outbox 메시지 저장 후 예외 발생 시 데이터 롤백 확인 (실제 Repository + get_current_session 사용), 트랜잭션 정상 완료 시 데이터 커밋 확인 |

### 실행

```bash
# Docker 실행 필수
TESTCONTAINERS_RYUK_DISABLED=true pytest tests/integration/ -v    # 31개, ~13분
```

---

## 6. 테스트 실행 방법

### 단위 테스트만 (가장 빠름)

```bash
# Domain + Application (0.1초)
pytest tests/domain/ tests/application/ -v
```

### 단위 + Adapter (Docker 필요)

```bash
# Domain + Application + Adapter (7초)
pytest tests/ --ignore=tests/integration -v
```

### 전체 (Docker 필요)

```bash
# 모든 테스트 (14분)
TESTCONTAINERS_RYUK_DISABLED=true pytest tests/ -v
```

### 레이어별

```bash
pytest tests/domain/ -v                # Domain 95개
pytest tests/application/ -v           # Application 107개
pytest tests/adapter/ -v               # Adapter 56개 (MySQL 컨테이너)
TESTCONTAINERS_RYUK_DISABLED=true \
  pytest tests/integration/ -v         # E2E 21개 (MySQL+MongoDB+Redis 컨테이너)
```
