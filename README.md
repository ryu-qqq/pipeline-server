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

### API 호출 예시

```bash
# 1. 분석 요청 → 202 반환, 비동기 정제 시작
curl -X POST http://localhost:8000/analyze

# 2. 진행 상태 확인 (task_id는 1번 응답에서 획득)
curl http://localhost:8000/analyze/{task_id}

# 3. 학습 데이터 검색
curl "http://localhost:8000/data?weather=sunny&object_class=car&min_obj_count=10"

# 4. 거부 데이터 조회
curl "http://localhost:8000/rejections?stage=selection&reason=invalid_format"
```

### 테스트

```bash
# 단위 테스트 (183개, 외부 의존 없음)
python -m pytest tests/domain/ tests/application/ tests/adapter/ -v

# 통합 테스트 (21개, Docker 필요 — testcontainers로 자동 관리)
python -m pytest tests/integration/ -v
```

### 종료

```bash
docker compose down -v
```

---

## 기술 스택 선택 이유

| 기술 | 선택 이유 |
|---|---|
| **Python 3.12 + FastAPI** | 비동기 지원, 자동 API 문서화(Swagger), Pydantic 기반 검증 |
| **MySQL 8.0** | 정제된 데이터의 복합 조건 검색(JOIN, 복합 인덱스), 트랜잭션 보장 |
| **MongoDB 7.0** | 원본 데이터 보관(스키마리스, 차량별 스키마 버전이 다를 수 있음), 작업 상태 관리, Replica Set 트랜잭션 |
| **Redis 7.0** | Celery 메시지 브로커, 검색 캐시(향후 확장) |
| **Celery** | 대용량 데이터 정제를 비동기로 처리, Beat 스케줄러로 Outbox 폴링 + 좀비 복구 |
| **SQLAlchemy** | ORM + Core 혼용, INSERT IGNORE 배치 처리 |
| **testcontainers** | 통합 테스트에서 실제 DB 컨테이너를 자동 관리 |

### Polyglot Persistence 설계

```
MongoDB (원본 보관)  →  정제 파이프라인  →  MySQL (학습 데이터)
  - raw_data                                - selections
  - analyze_tasks                           - odd_tags
  - outbox                                  - labels
                                            - rejections
```

- **MongoDB**: 원본 데이터를 스키마리스로 보관하여 차량별 수집 소프트웨어 버전 차이를 흡수. 정제 실패 시 원본에서 재처리 가능.
- **MySQL**: 정제 완료된 데이터를 정규화하여 복합 조건 검색(날씨 + 노면 + 객체 탐지)에 최적화.
- **크로스 저장소 일관성**: Transactional Outbox 패턴 + resume 로직(last_completed_phase)으로 보상. 프로덕션에서는 2PC 또는 Saga 패턴으로 확장 가능.

---

## 아키텍처

### DDD + Hexagonal Architecture

```
app/
├── domain/              # 핵심 비즈니스 규칙 (순수 Python)
│   ├── models.py        # Selection, OddTag, Label, AnalyzeTask, OutboxMessage 등
│   ├── value_objects.py # VideoId, Temperature, Confidence 등 (불변, 자체 검증)
│   ├── enums.py         # Weather, Stage, TaskStatus, RejectionReason 등
│   ├── exceptions.py    # DomainError 계층 (ConflictError, DataNotFoundError 등)
│   └── ports.py         # Repository ABC (Port) — save/find만 정의
│
├── application/         # 유스케이스 조율
│   ├── analysis_service.py      # POST /analyze — 적재 + Task/Outbox 생성
│   ├── pipeline_service.py      # 정제 오케스트레이터 (Phase 순서 + resume)
│   ├── phase_runners.py         # PhaseRunner ABC + Provider (Selection/OddTag/Label)
│   ├── selection_refiner.py     # Selection 정제 (V1/V2 스키마 자동 감지)
│   ├── odd_tag_refiner.py       # ODD 태깅 정제 (필드별 에러 수집)
│   ├── label_refiner.py         # 자동 라벨링 정제 (소수점/음수 검증)
│   ├── outbox_relay_service.py  # Outbox 발행 + 좀비 복구
│   ├── data_read_service.py     # GET /data — 학습 데이터 검색
│   ├── task_read_service.py     # GET /analyze/{id} — 진행 상태 조회
│   └── rejection_read_service.py # GET /rejections — 거부 데이터 조회
│
├── adapter/
│   ├── inbound/
│   │   ├── rest/        # FastAPI 라우터 + Pydantic 스키마 + Mapper
│   │   └── worker/      # Celery task (pipeline_task, outbox_poller_task)
│   └── outbound/
│       ├── mysql/       # Entity + Mapper + Repository + QueryBuilder
│       ├── mongodb/     # Document + Mapper + Repository + Transaction
│       ├── redis/       # CacheRepository
│       └── celery/      # TaskDispatcher
│
├── dependencies.py      # DI 팩토리 함수 (FastAPI Depends 체인)
├── main.py              # FastAPI 앱 + 글로벌 예외 핸들러
└── worker.py            # Celery 앱 + Beat 스케줄
```

### 핵심 설계 원칙

- **의존성 방향**: adapter/inbound → application → domain ← adapter/outbound
- **도메인 순수성**: domain 레이어는 순수 Python만 사용 (FastAPI, SQLAlchemy 의존 없음)
- **Repository는 저장/조회만**: 상태 전이는 도메인 객체가 담당, Repository는 save(upsert) + find
- **도메인 객체 불변**: `@dataclass(frozen=True)`, 상태 변경 시 `dataclasses.replace`로 새 인스턴스 반환

---

## 데이터 정제 파이프라인

### 전체 흐름

```
POST /analyze
  → AnalysisService: 파일 적재(MongoDB) + Task/Outbox 생성 (@transactional)
  → 202 Accepted

Celery Beat (5초)
  → OutboxRelayService: PENDING → PROCESSING → dispatch → PUBLISHED

Celery Worker
  → PipelineService: Phase 순서 제어
    → SelectionPhaseRunner: V1/V2 파서 자동 감지 → MySQL INSERT IGNORE
    → OddTagPhaseRunner: Enum 검증 → MySQL INSERT IGNORE
    → LabelPhaseRunner: 범위/소수점 검증 → MySQL INSERT IGNORE
  → Task COMPLETED + 캐시 무효화
```

### 방어적 처리

| 예외 상황 | 처리 방식 |
|---|---|
| **V1/V2 스키마 혼재** | `SelectionRefiner`가 스키마 자동 감지 (sensor 필드 유무) |
| **필드 누락/잘못된 값** | 필드별 에러 수집 — 한 row에서 에러 3개면 Rejection 3건 |
| **중복 데이터** | MySQL UNIQUE INDEX + INSERT IGNORE — DB가 중복 탐지 |
| **파일 없음/JSON 깨짐** | `DataNotFoundError`, `InvalidFormatError` → 400 응답 |
| **중복 분석 요청** | 진행 중인 Task 존재 시 `ConflictError` → 409 응답 |
| **파이프라인 중간 실패** | `last_completed_phase` 기록 → 재시도 시 완료된 Phase 건너뜀 (resume) |
| **Outbox 발행 실패** | PROCESSING 상태로 남겨 좀비 복구 스케줄러(1분)가 PENDING으로 복구 |
| **RFC 7807 에러 응답** | 모든 에러가 `ProblemDetail` 형식으로 통일 |

### 거부 사유 분류 체계

| Reason | 설명 | 예시 |
|---|---|---|
| `unknown_schema` | 인식 불가 스키마 | V1도 V2도 아닌 JSON |
| `invalid_format` | 필드 파싱 실패 | video_id가 문자열 |
| `missing_required_field` | 필수 필드 누락 | weather 없음 |
| `invalid_enum_value` | 허용되지 않은 Enum | weather=tornado |
| `fractional_obj_count` | 객체 수 소수점 | obj_count=5.5 |
| `negative_obj_count` | 객체 수 음수 | obj_count=-1 |
| `duplicate_tagging` | ODD 태깅 중복 | 동일 video_id |
| `duplicate_label` | 라벨 중복 | 동일 video_id + class |

---

## 대용량 처리 전략

| 전략 | 구현 |
|---|---|
| **스트리밍 조회** | MongoDB cursor를 Iterator로 반환, 전체를 메모리에 올리지 않음 |
| **청크 단위 적재** | 5,000건씩 배치 INSERT, 생성자 주입으로 튜닝 가능 |
| **INSERT IGNORE** | UNIQUE 위반 시 건별 재시도 없이 배치 한 방에 처리, rowcount로 중복 건수 파악 |
| **Phase 단위 진행률** | MongoDB upsert를 청크마다가 아닌 Phase 완료 시 1번만 (3번/파이프라인) |
| **task_id별 데이터 격리** | DELETE ALL 없이 데이터 누적, 조회 시 task_id 필터 |
| **복합 인덱스** | 검색 쿼리 패턴에 맞춘 covering index (ODD search, Label search, Rejection filter) |

### 성능 수치 (docker-compose 환경, M1 Mac)

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

현재 구현에서 의도적으로 확장 포인트를 남겨둔 부분:

| 영역 | 현재 | 확장 방향 |
|---|---|---|
| **검색 엔진** | MySQL 복합 인덱스 + QueryBuilder | Elasticsearch 도입 시 `DataSearchRepository` 구현체만 교체 |
| **실시간 진행률** | Phase 단위 폴링 (`GET /analyze/{id}`) | WebSocket/SSE로 실시간 푸시 |
| **캐시** | 캐시 무효화만 구현 (`invalidate_all`) | Repository 데코레이터 패턴으로 읽기 캐시 적용 |
| **Phase 추가** | PhaseRunnerProvider에 등록 | 새 PhaseRunner 구현 + Provider 등록만으로 Phase 추가 |
| **Rejection 집계** | 건건이 저장 + API 필터링 | 별도 배치 스케줄러로 Summary 테이블 집계 |
| **크로스 저장소 일관성** | resume 로직 (보상 패턴) | 2PC 또는 Saga 패턴 |
| **중복 요청 방어** | 진행 중 Task 존재 시 거부 | 멱등키 기반 처리, 파일 해시 기반 중복 감지 |

---

## 테스트

```
tests/
├── domain/              # 56개 — 도메인 모델, Value Object 불변식
├── application/         # 81개 — Refiner, Service, Pipeline (Mock Repository)
├── adapter/             # 46개 — Router, Mapper, QueryBuilder, Repository (SQLite)
└── integration/         # 21개 — E2E 시나리오 (testcontainers: MySQL + MongoDB + Redis)
                         ─────
                         204개 전체 통과
```

### 테스트 전략

| 레이어 | 방식 | 외부 의존 |
|---|---|---|
| Domain | 순수 Python, 외부 의존 없음 | 없음 |
| Application | `MagicMock(spec=Repository)` | 없음 |
| Adapter | SQLite in-memory + FastAPI TestClient | 없음 |
| Integration | testcontainers (MySQL + MongoDB + Redis) | Docker |

### 통합 테스트 시나리오

1. **전체 파이프라인 Happy Path** — POST /analyze → Outbox → Pipeline → COMPLETED → 검색/거부 조회
2. **중복 요청 방어** — 두 번째 POST → 409, 완료 후 재요청 → 202
3. **데이터 품질 검증** — 거부 사유별 분류 정확성 + 필터링
4. **task_id별 데이터 격리** — 두 건의 분석 후 각각 격리 조회

---

## AI 활용

이 프로젝트는 Claude Code(Anthropic)를 활용하여 개발했습니다.
상세한 프롬프트와 의사결정 과정은 `CLAUDE.md`에 포함되어 있습니다.
