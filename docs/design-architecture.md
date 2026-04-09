# 아키텍처 설계 문서

## 1. 개요

자율주행 영상 데이터 정제·분석 파이프라인 서버.
3개 파일(selections.json, odds.csv, labels.csv)을 수집 → 정제 → 적재 → 검색하는 전체 흐름을 구현한다.

### 설계 원칙
- **Write Path / Read Path 분리** (CQRS + Polyglot Persistence)
- **비동기 파이프라인** (Celery Worker 기반)
- **도메인 주도 설계** (Hexagonal Architecture + DDD)

---

## 2. 아키텍처 다이어그램

```
                    ┌─────────────────────────────────┐
                    │          Client (ML 엔지니어)     │
                    └──────────┬──────────┬────────────┘
                               │          │
                    POST /analyze    GET /search
                    (데이터 유입)     GET /rejections
                               │     GET /analyze/{task_id}
                               │          │
                    ┌──────────▼──────────▼────────────┐
                    │        FastAPI (app)               │
                    │  routers → services → ports(ABC)   │
                    └──────┬─────────┬─────────┬────────┘
                           │         │         │
              Write Path   │         │         │   Read Path
                           │         │         │
                    ┌──────▼──┐  ┌───▼───┐  ┌──▼───────┐
                    │ MongoDB │  │ Redis │  │  MySQL    │
                    │         │  │       │  │          │
                    │ raw_data│  │ task  │  │selections│
                    │ analyze │  │ status│  │odd_tags  │
                    │ _tasks  │  │       │  │labels    │
                    │         │  │ search│  │rejections│
                    │         │  │ cache │  │          │
                    └──────┬──┘  └───────┘  └──▲───────┘
                           │                    │
                    ┌──────▼────────────────────┤
                    │     Celery Worker          │
                    │                            │
                    │  MongoDB에서 읽기           │
                    │  → 정제 (파서 + 검증기)      │
                    │  → MySQL에 적재             │
                    │  → 진행률 업데이트 (Redis)    │
                    └───────────────────────────┘
```

---

## 3. 기술 스택

| 구성 요소 | 기술 | 역할 | 선택 이유 |
|---|---|---|---|
| **API 서버** | FastAPI | HTTP API, Swagger 자동 생성 | 비동기 지원, 타입 힌트 기반 |
| **Write DB** | MongoDB 7.0 | 원본 데이터 적재, 작업 상태 | 스키마 유연, 쓰기 최적화, JD 우대 |
| **Read DB** | MySQL 8.0 | 정제된 데이터 저장, 검색 | 정형 데이터, JOIN, 인덱스 |
| **캐시/브로커** | Redis 7.0 | Celery 브로커, 작업 상태, 검색 캐시 | 인메모리 속도, Pub/Sub |
| **비동기 워커** | Celery | 정제 파이프라인 비동기 처리 | 분산 태스크 큐 표준 |
| **ORM** | SQLAlchemy 2.0 | MySQL 접근 | Python ORM 표준 |
| **ODM** | PyMongo | MongoDB 접근 | MongoDB 공식 드라이버 |
| **컨테이너** | Docker Compose | 전체 인프라 구성 | 한 방 실행 |

---

## 4. Docker Compose 구성

```yaml
services:
  mysql:        # Read Path — 정제된 데이터 + 검색
  mongodb:      # Write Path — 원본 데이터 + 작업 추적
  redis:        # 메시지 브로커 + 캐시
  app:          # FastAPI 서버
  worker:       # Celery worker (같은 코드, 다른 진입점)
```

---

## 5. API 설계

### POST /analyze
```
요청: (없음 — 서버에 있는 data/ 디렉토리의 3개 파일을 처리)

흐름:
  1. 3개 파일을 MongoDB raw_data에 벌크 저장 (스키마 검증 없이 빠르게)
  2. analyze_tasks에 작업 생성 (status=pending)
  3. Celery task 발행
  4. 즉시 202 반환

응답 (202 Accepted):
{
    "data": {
        "task_id": "abc-123",
        "status": "pending"
    },
    "timestamp": "2026-04-09 12:00:00",
    "request_id": "uuid"
}
```

### GET /analyze/{task_id}
```
흐름: MongoDB analyze_tasks에서 상태 조회

응답 (진행 중):
{
    "data": {
        "task_id": "abc-123",
        "status": "processing",
        "progress": {
            "selection": { "total": 98776, "processed": 45000, "rejected": 0, "percent": 45.5 },
            "odd_tagging": { "total": 0, "processed": 0, "rejected": 0, "percent": 0 },
            "auto_labeling": { "total": 0, "processed": 0, "rejected": 0, "percent": 0 }
        },
        "created_at": "2026-04-09T12:00:00",
        "completed_at": null
    }
}

응답 (완료):
{
    "data": {
        "task_id": "abc-123",
        "status": "completed",
        "progress": { ... },
        "result": {
            "selection": { "total": 98776, "loaded": 98776, "rejected": 0 },
            "odd_tagging": { "total": 96799, "loaded": 96759, "rejected": 40 },
            "auto_labeling": { "total": 322856, "loaded": 322791, "rejected": 65 },
            "fully_linked": 95035,
            "partial": 3741
        },
        "created_at": "2026-04-09T12:00:00",
        "completed_at": "2026-04-09T12:00:15"
    }
}
```

### GET /rejections
```
Query params: stage, reason, page, size (기존과 동일)
MySQL에서 조회. 기존 구현 유지.
```

### GET /search
```
Query params: weather, time_of_day, road_surface, object_class, min_obj_count, min_confidence, page, size

흐름:
  1. Redis 캐시 확인 (검색 조건 hash)
  2. 캐시 히트 → 즉시 반환
  3. 캐시 미스 → MySQL QueryBuilder 실행 → Redis에 캐싱 (TTL 5분)

MySQL에서 조회. 기존 QueryBuilder 유지.
```

---

## 6. MongoDB 스키마 설계

### raw_data 컬렉션
```json
{
    "_id": ObjectId,
    "task_id": "abc-123",
    "source": "selections",
    "data": { "id": 1, "recordedAt": "...", "sensor": { ... } },
    "created_at": "2026-04-09T12:00:00"
}
```
- 인덱스: `{ task_id: 1, source: 1 }`
- 원본 그대로 저장 (정제 전)
- Celery worker가 task_id + source로 읽어서 정제

### analyze_tasks 컬렉션
```json
{
    "_id": "abc-123",
    "status": "processing",
    "progress": {
        "selection": { "total": 98776, "processed": 45000, "rejected": 0 },
        "odd_tagging": { "total": 0, "processed": 0, "rejected": 0 },
        "auto_labeling": { "total": 0, "processed": 0, "rejected": 0 }
    },
    "result": null,
    "error": null,
    "created_at": "2026-04-09T12:00:00",
    "completed_at": null
}
```
- 인덱스: `{ status: 1 }`
- 작업 상태 추적 + 진행률 업데이트

---

## 7. MySQL 인덱스 설계

```sql
-- selections: PK로 충분 (id = video_id로 JOIN)
-- PK: id

-- odd_tags: video_id로 JOIN + 필터링
-- UNIQUE: video_id
-- 복합 인덱스: (weather, time_of_day, road_surface) — 검색 필터 조합
CREATE INDEX ix_odd_tags_search ON odd_tags (weather, time_of_day, road_surface);

-- labels: video_id로 JOIN + object_class 필터
-- UNIQUE: (video_id, object_class)
-- 복합 인덱스: (object_class, obj_count) — 검색 서브쿼리 최적화
CREATE INDEX ix_labels_search ON labels (object_class, obj_count);

-- rejections: stage + reason 필터
-- 인덱스: stage, reason (이미 있음)
```

---

## 8. Celery Worker 파이프라인

```
Task: process_analysis(task_id)
  │
  ├── Phase 1: Selection 정제
  │   ├── MongoDB raw_data에서 source=selections, task_id=xxx 조회
  │   ├── 청크(5000건)씩 읽기
  │   ├── 각 청크: detect_parser → parse → Selection 도메인 모델
  │   ├── 성공 → MySQL selections 벌크 적재
  │   ├── 실패 → MySQL rejections 적재
  │   └── 진행률 업데이트 → MongoDB analyze_tasks
  │
  ├── Phase 2: ODD 정제
  │   ├── MongoDB raw_data에서 source=odds 조회
  │   ├── OddValidator.validate_batch()
  │   ├── 성공 → MySQL odd_tags 적재
  │   ├── 실패 → MySQL rejections 적재
  │   └── 진행률 업데이트
  │
  ├── Phase 3: Label 정제
  │   ├── MongoDB raw_data에서 source=labels 조회
  │   ├── LabelValidator.validate_batch()
  │   ├── 성공 → MySQL labels 적재
  │   ├── 실패 → MySQL rejections 적재
  │   └── 진행률 업데이트
  │
  └── 완료
      ├── 통합 통계 계산 (fully_linked, partial)
      ├── analyze_tasks.status = completed
      └── analyze_tasks.result = AnalysisResult
```

---

## 9. Redis 사용

### 검색 캐시
```
key: search:{conditions_hash}
value: JSON 응답
TTL: 300초 (5분)

POST /analyze 완료 시 → 전체 캐시 무효화 (데이터가 변경됐으므로)
```

### 작업 상태 (선택적 — MongoDB로도 충분)
```
key: task:{task_id}:status
value: "processing" | "completed" | "failed"
TTL: 3600초 (1시간)
```

---

## 10. 프로젝트 구조 (변경 후)

```
app/
├── domain/                          # 순수 Python (변경 없음)
│   ├── enums.py
│   ├── models.py
│   ├── value_objects.py
│   ├── exceptions.py
│   └── ports.py                     # + MongoRawDataRepository, TaskRepository 추가
│
├── application/                     # 비즈니스 로직
│   ├── analysis_service.py          # 리팩토링: MongoDB 적재 + Celery 발행
│   ├── pipeline_worker.py           # 신규: Celery task (정제 파이프라인)
│   ├── task_service.py              # 신규: 작업 상태 조회
│   ├── rejection_service.py
│   ├── search_service.py
│   ├── parsers.py
│   └── validators.py
│
├── adapter/
│   ├── inbound/
│   │   ├── routers.py               # + POST /analyze 202, GET /analyze/{task_id}
│   │   ├── schemas.py               # + TaskResponse, TaskProgressResponse
│   │   └── mappers.py
│   └── outbound/
│       ├── database.py              # MySQL (기존)
│       ├── mongodb.py               # 신규: MongoDB 연결
│       ├── redis_client.py          # 신규: Redis 연결
│       ├── entities.py              # MySQL Entity (기존)
│       ├── mongo_repositories.py    # 신규: MongoDB Repository 구현
│       ├── repositories.py          # MySQL Repository (기존)
│       ├── query_builder.py
│       └── mappers.py
│
├── worker.py                        # Celery 앱 진입점
├── dependencies.py
└── main.py

docker-compose.yml                   # MySQL + MongoDB + Redis + App + Worker
Dockerfile                           # 공통 이미지 (app, worker 모두 사용)
```

---

## 11. 구현 일정

### Day 1: 인프라 + 비동기 기반
- [ ] docker-compose.yml: MongoDB + Redis 추가
- [ ] pymongo, redis, celery 설치
- [ ] MongoDB 연결 (mongodb.py)
- [ ] Redis 연결 (redis_client.py)
- [ ] Celery 앱 설정 (worker.py)
- [ ] MongoDB Repository (raw_data, analyze_tasks)
- [ ] domain/ports.py: RawDataRepository, TaskRepository ABC 추가

### Day 2: 파이프라인 워커 + API 변경
- [ ] pipeline_worker.py: Celery task 구현 (기존 정제 로직 이관)
- [ ] analysis_service.py: MongoDB 적재 + Celery 발행으로 변경
- [ ] task_service.py: 작업 상태 조회
- [ ] routers.py: POST /analyze → 202, GET /analyze/{task_id}
- [ ] schemas.py: TaskResponse, TaskProgressResponse 추가
- [ ] Redis 검색 캐시 적용

### Day 3: 테스트 코드
- [ ] domain 단위 테스트 (VO, Rich Domain Model, 예외)
- [ ] application 단위 테스트 (파서, 검증기, 서비스 Mock)
- [ ] adapter 통합 테스트 (MySQL Repository, API TestClient)
- [ ] 파이프라인 E2E 테스트

### Day 4: 문서 + 코드 정리
- [ ] README.md (실행 방법, 설계 근거, 라이브러리 선택 이유)
- [ ] 컨벤션 문서 업데이트
- [ ] 데이터 분석 문서 정리
- [ ] CLAUDE.md (AI 활용 프롬프트)
- [ ] Ruff 린트 + 포맷 최종 정리

### Day 5: 최종 검증 + 버퍼
- [ ] docker-compose up 한 방 실행 테스트
- [ ] 전체 API 시나리오 테스트
- [ ] 엣지 케이스 검증
- [ ] 제출물 패키징 (.git 포함)
