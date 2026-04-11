# Pipeline Server

자율주행 영상 데이터의 **정제 → 통합 → 분석 API**를 제공하는 파이프라인 서버입니다.

3개 원본 파일(Selection, ODD Tagging, Auto Labeling)을 읽어 데이터 품질을 검증하고, 정제된 학습 데이터셋을 ML 엔지니어가 다양한 조건으로 검색할 수 있도록 합니다.

---

## 실행 방법

### 사전 요구사항
- Docker, Docker Compose

### 실행

```bash
docker compose up --build -d
```

5개 컨테이너가 순서대로 시작됩니다:
1. **MySQL 8.0** — 정제된 학습 데이터 저장
2. **MongoDB 7.0** (Replica Set) — 원본 데이터 보관 + 작업 상태 관리
3. **Redis 7.0** — Celery 메시지 브로커
4. **app** — FastAPI 서버 (http://localhost:8000)
5. **worker** — Celery Worker + Beat (비동기 정제 파이프라인 + Outbox 폴링)

### API 문서

서버 실행 후 아래 URL에서 API 문서를 확인할 수 있습니다:

| URL | 설명 |
|---|---|
| http://localhost:8000/docs | **Swagger UI** — 인터랙티브 API 테스트 |
| http://localhost:8000/redoc | **ReDoc** — 깔끔한 API 레퍼런스 문서 |
| http://localhost:8000/openapi.json | **OpenAPI 3.0 스펙** (JSON) |

### API 호출 예시

```bash
# 1. 분석 요청 → 202 반환, 비동기 정제 시작
curl -X POST http://localhost:8000/analyze

# 2. 진행 상태 확인 (task_id는 1번 응답에서 획득)
curl http://localhost:8000/analyze/{task_id}

# 3. 학습 데이터 검색 (offset 페이징)
curl "http://localhost:8000/data?weather=sunny&object_class=car&min_obj_count=10&page=1&size=20"

# 3-1. 학습 데이터 검색 (cursor 페이징 — 대용량 뒤쪽 페이지 성능 최적화)
curl "http://localhost:8000/data?weather=sunny&after=0&size=20"

# 4. 거부 데이터 조회
curl "http://localhost:8000/rejections?stage=selection&reason=invalid_format"
```

### 테스트

```bash
# 전체 테스트 (Docker 필요)
python -m pytest tests/ -v

# 도메인 단위 테스트 (외부 의존 없음)
python -m pytest tests/domain/ -v

# Application 단위 테스트 (Mock Repository)
python -m pytest tests/application/ -v

# Adapter 단위 테스트 (SQLite in-memory + TestClient)
python -m pytest tests/adapter/ -v

# 통합 E2E 테스트 (testcontainers — MySQL + MongoDB + Redis)
python -m pytest tests/integration/ -v
```

### 종료

```bash
docker compose down -v
```

---

## 설계 과정

데이터를 먼저 분석하고, 분석 결과를 토대로 모델링과 아키텍처를 결정했습니다.

| 단계 | 산출물 | 설명 |
|---|---|---|
| 1. 데이터 탐색 | [`notebooks/data-analysis.ipynb`](notebooks/data-analysis.ipynb) | Jupyter Notebook으로 3개 파일의 스키마 변형, 노이즈 패턴, 중복, ID 관계를 시각화 |
| 2. 분석 결과 정리 | [`docs/data-analysis.md`](docs/data-analysis.md) | V1/V2 스키마 비율, 온도 단위 불일치, 거부 사유 분류 체계 도출 |
| 3. 데이터 모델 설계 | [`docs/data-model.md`](docs/data-model.md) | ERD, 인덱스 설계, MongoDB 컬렉션 구조, Enum 허용값 |
| 4. 아키텍처 설계 | [`docs/architecture.md`](docs/architecture.md) | DDD + Hexagonal, 데이터 흐름, Polyglot Persistence, 비동기 파이프라인 |
| 5. 테스트 전략 | [`docs/testing-strategy.md`](docs/testing-strategy.md) | 테스트 피라미드, 레이어별 전략, 커버리지 분석 |

---

## 기술 스택 선택 이유

| 기술 | 선택 이유 |
|---|---|
| **Python 3.12 + FastAPI** | 비동기 지원, 자동 API 문서화(Swagger/ReDoc), Pydantic 기반 검증 |
| **MySQL 8.0** | 정제된 데이터의 복합 조건 검색(JOIN, 복합 인덱스), 트랜잭션 보장 |
| **MongoDB 7.0** | 원본 데이터 보관(스키마리스), 작업 상태 관리, Replica Set 트랜잭션 |
| **Redis 7.0** | Celery 메시지 브로커 |
| **Celery** | 대용량 데이터 정제를 비동기로 처리, Beat 스케줄러로 Outbox 폴링 + 좀비 복구 |
| **SQLAlchemy** | ORM + Core 혼용, INSERT IGNORE 배치 처리 |
| **testcontainers** | 통합 테스트에서 실제 DB 컨테이너를 자동 관리 |

> 아키텍처 상세(DDD + Hexagonal, Polyglot Persistence, 비동기 파이프라인)는 [`docs/architecture.md`](docs/architecture.md)를 참조하세요.

---

## 방어적 처리

### API 레벨

| HTTP | 상황 | 처리 |
|---|---|---|
| **409** | 이미 진행 중인 분석 작업이 존재 | `ConflictError` — 중복 요청 차단 |
| **400** | 파일 없음, JSON 깨짐, CSV 파싱 실패 | `DataNotFoundError`, `InvalidFormatError` |
| **400** | page + after 동시 요청 | Pydantic `model_validator`로 차단 |
| **400** | 유효하지 않은 Enum 값 (weather=tornado) | FastAPI 자동 검증 |
| **400** | 존재하지 않는 task_id 조회 | `DataNotFoundError` |
| **all** | 모든 에러 응답 | RFC 7807 `ProblemDetail` 형식 통일 |

### 정제 파이프라인 레벨

| 상황 | 처리 |
|---|---|
| **V1/V2 스키마 혼재** | `SelectionRefiner`가 `sensor` 필드 유무로 자동 감지. V1(섭씨) / V2(화씨→섭씨 변환) |
| **필드별 에러 수집** | 한 row에서 에러가 여러 개면 **에러별로 각각 Rejection 생성** (첫 에러만 잡히지 않음) |
| **중복 데이터** | MySQL `UNIQUE INDEX` + `INSERT IGNORE` — DB가 중복을 탐지하고 rowcount로 건수 파악 |
| **파이프라인 중간 실패** | `last_completed_phase`에 체크포인트 기록 → Celery 재시도 시 완료된 Phase 건너뜀 |
| **Outbox 발행 실패** | PROCESSING 상태 유지 → 좀비 복구 스케줄러(1분)가 PENDING으로 복구 또는 FAILED 처리 |

### 거부 사유 분류 체계

Rejection은 `task_id` + `stage` + `reason` + `source_id` + `field`로 구조화하여, **어떤 작업의 어떤 단계에서 어떤 원본의 어떤 필드가 왜 실패했는지** 추적할 수 있습니다.

**스키마/포맷 오류**

| Reason | 발생 단계 | 설명 |
|---|---|---|
| `unknown_schema` | Selection | V1(flat)도 V2(sensor)도 아닌 인식 불가 구조 |
| `invalid_format` | 전 단계 | 필드 값 파싱 실패 (video_id가 문자열, 날짜 형식 오류 등) |
| `missing_required_field` | 전 단계 | 필수 필드 누락 (weather, time_of_day 등) |

**값 범위 오류**

| Reason | 발생 단계 | 설명 |
|---|---|---|
| `invalid_enum_value` | ODD, Label | 허용 범위 밖의 Enum 값 (weather=tornado) |
| `fractional_obj_count` | Label | 객체 수가 정수가 아님 (obj_count=5.5) |
| `negative_obj_count` | Label | 객체 수가 음수 (obj_count=-1) |

**중복 오류**

| Reason | 발생 단계 | 설명 |
|---|---|---|
| `duplicate_tagging` | ODD | 동일 task + video_id에 태깅 2건 이상 (UNIQUE 위반) |
| `duplicate_label` | Label | 동일 task + video_id + object_class 조합 중복 (UNIQUE 위반) |

---

## 대용량 처리 전략

### 쓰기: "검증은 DB에 위임하고, 애플리케이션은 밀어넣기만 한다"

51만 건의 데이터를 정제할 때 가장 큰 병목은 **중복 탐지**입니다. 애플리케이션에서 `Counter`로 중복을 찾으면 전체 데이터를 메모리에 올려야 하고, 이미 DB에 있는 데이터와의 중복도 별도 조회가 필요합니다.

이 문제를 **MySQL UNIQUE INDEX + INSERT IGNORE**로 해결했습니다:
- 애플리케이션은 검증된 데이터를 **조회 없이 바로 INSERT**
- DB가 UNIQUE 제약으로 중복을 자동 거부하고, `rowcount`로 실제 적재 건수를 반환
- 건별 INSERT 재시도 루프가 없으므로 **DB 호출 횟수 = 청크 수**

### 읽기: "전체를 메모리에 올리지 않는다"

MongoDB에서 원본 데이터를 조회할 때 `list[dict]`로 반환하면 10만 건이 한 번에 메모리에 올라갑니다. 이를 **Iterator(cursor 스트리밍)**로 변경하여, 5,000건 청크 단위로 읽고 → 정제하고 → 적재하는 사이클을 반복합니다. 메모리에는 항상 청크 크기만큼만 유지됩니다.

### 상태 관리: "불필요한 DB 호출을 줄인다"

진행률을 청크마다 MongoDB에 upsert하면 10만 건 / 5,000청크 = 20번 × 3 Phase = **60번의 upsert**가 발생합니다. Phase 완료 시 1번만 갱신하도록 변경하여 **3번으로 축소**했습니다.

### 데이터 격리: "삭제하지 않고 쌓는다"

기존에는 `DELETE ALL → INSERT ALL`로 재분석 시 기존 데이터를 삭제했습니다. 이는 분석 중 실패하면 MySQL이 빈 상태로 남는 위험이 있고, 과거 분석 이력도 사라집니다. 모든 테이블에 `task_id` 컬럼을 추가하여 **삭제 없이 task별로 격리 조회**합니다.

### 검색: "대용량 뒤쪽 페이지에서도 일정한 성능"

`OFFSET 16000`은 앞의 16,000건을 읽고 버려야 합니다. cursor 기반 페이징(`WHERE id > after`)을 도입하여 인덱스로 바로 접근합니다. offset과 cursor 두 방식을 동시 지원하되, 동시 사용 시 400 에러로 거부합니다.

### 성능 수치

> 환경: docker-compose, Apple M5 Pro MacBook Pro 16 (RAM 24GB)

| 항목 | 수치 |
|---|---|
| Selection 정제 | 98,776건 |
| ODD Tagging 정제 | 96,799건 (1건 거부) |
| Auto Labeling 정제 | 322,856건 (26건 거부) |
| **총 처리량** | **518,431건** |
| **총 소요시간** | **약 28초** |
| fully_linked | 95,054건 |

---

## 확장 가능성

현재 구현에서 **Port 추상화와 Provider 패턴**을 통해 의도적으로 확장 포인트를 남겨둔 부분입니다.

### 검색 고도화

현재 MySQL 복합 인덱스 + QueryBuilder로 검색하고 있으나, 데이터가 수백만 건 이상이거나 복합 조건이 더 복잡해지면 **Elasticsearch** 도입을 고려합니다. `DataSearchRepository` Port가 추상화되어 있으므로 구현체만 교체하면 됩니다.

### Outbox 폴링 → CDC (Change Data Capture)

현재는 Celery Beat가 5초마다 Outbox 컬렉션을 폴링합니다. 프로덕션에서는 MongoDB의 **Change Stream**(CDC)으로 Outbox 변경을 실시간 감지하고, Kafka 같은 메시지 브로커에 이벤트를 발행하는 구조로 전환합니다. Outbox 도메인 모델과 Application 서비스 코드는 그대로 유지되며, Adapter-In만 교체하면 됩니다.

### 실시간 진행률

현재 Phase 단위 폴링(`GET /analyze/{id}`)으로 진행률을 확인합니다. WebSocket 또는 SSE(Server-Sent Events)를 도입하면 클라이언트에 실시간으로 푸시할 수 있습니다.

### Phase 추가

새로운 정제 단계가 추가될 때 `PhaseRunner`를 구현하고 `PhaseRunnerProvider`에 등록하면 됩니다. `PipelineService`의 오케스트레이션 코드는 변경하지 않습니다.

### Rejection 집계

현재 Rejection을 건건이 저장하고 API로 필터링합니다. 데이터가 대량이면 별도 배치 스케줄러가 `task_id + stage + reason`별로 Summary를 집계하여 대시보드에 활용할 수 있습니다.

### 크로스 저장소 일관성

현재 MongoDB(원본) → MySQL(정제) 간 일관성은 resume 보상 패턴으로 처리합니다. 프로덕션에서 더 강한 보장이 필요하면 2PC 또는 Saga 패턴으로 확장할 수 있습니다.

---

## AI 활용

이 프로젝트는 **Claude Code(Anthropic CLI)**를 활용하여 개발했습니다.
아키텍처 결정, 데이터 분석 해석, 정제 전략 등 설계 판단은 직접 수행했습니다.

- AI 활용 기록 + 핵심 의사결정: [`docs/ai-usage-log.md`](docs/ai-usage-log.md)
- AI에게 내린 프로젝트 컨텍스트: [`.claude/CLAUDE.md`](.claude/CLAUDE.md)
