# README.md 구성 초안

> 이 문서는 README 작성 시 참고할 내용 목록. 최종 README는 이 구조를 기반으로 작성한다.

---

## 1. 프로젝트 소개
- 자율주행 영상 데이터 정제·분석 파이프라인 서버
- 3개 파일(selections.json, odds.csv, labels.csv)을 수집 → 정제 → 적재 → 검색

---

## 2. 실행 방법

```bash
# 전체 서비스 실행 (MySQL + MongoDB + Redis + App + Worker)
docker-compose up --build

# API 문서
http://localhost:8000/docs

# 분석 실행
curl -X POST http://localhost:8000/analyze

# 진행률 조회
curl http://localhost:8000/analyze/{task_id}

# 검색
curl "http://localhost:8000/search?weather=sunny&object_class=pedestrian&min_obj_count=10"

# 거부 데이터 조회
curl "http://localhost:8000/rejections?stage=auto_labeling&reason=negative_obj_count"
```

---

## 3. 기술 스택 + 선택 이유

| 기술 | 역할 | 선택 이유 |
|---|---|---|
| Python 3.12 | 언어 | JD 자격요건 + 최신 안정 버전 (제네릭 신문법, StrEnum) |
| FastAPI | API 서버 | 비동기 지원, 타입 힌트 기반, Swagger 자동 생성 |
| MySQL 8.0 | Read Path | 정형 데이터, JOIN + 인덱스 최적화, 복합 필터링 검색 |
| MongoDB 7.0 | Write Path | 스키마 유연, 쓰기 최적화, JD 우대사항 직접 대응 |
| Redis 7.0 | 캐시 + 브로커 | 검색 결과 캐싱(TTL 5분), Celery 메시지 브로커 |
| Celery | 비동기 워커 | 분산 태스크 큐 표준, EKS에서 Pod 스케일 아웃 가능 |
| SQLAlchemy 2.0 | ORM | Python ORM 표준, 커넥션 풀(QueuePool) 내장 |
| PyMongo | MongoDB 드라이버 | 공식 드라이버 |
| Pydantic 2 | API DTO | Bean Validation + 직렬화 통합 |
| pytest | 테스트 | Python 테스트 표준 |
| Ruff | 린터 + 포매터 | Checkstyle + Spotless + Flake8 통합 (단일 도구) |
| Docker Compose | 인프라 | 한 방 실행, 리뷰어 편의 |

---

## 4. 아키텍처

### 4-1. CQRS + Polyglot Persistence

```
Write Path: 파일 → MongoDB (원본 적재) → Celery Worker (정제) → MySQL
Read Path:  ML 엔지니어 → GET /search → MySQL (QueryBuilder) + Redis (캐시)
```

### 4-2. Outbox 패턴

- 현재: Celery Beat 5초 주기 폴링으로 outbox 메시지 발행
- MongoDB에 task + outbox를 같은 DB에 저장하여 순서 보장
- 프로덕션 고려:
  - CDC(Change Data Capture): MongoDB Change Stream으로 실시간 감지 가능
  - Change Stream은 Replica Set 필수 → 과제 환경(단일 노드)에서는 폴링 선택
  - CDC 전환 시 OutboxRelayService만 교체 (Port 추상화 덕분)

### 4-3. 비동기 파이프라인

- POST /analyze → 202 Accepted (즉시 반환)
- Outbox Poller가 메시지 감지 → Celery Worker에 발행
- GET /analyze/{task_id}로 진행률 실시간 조회
- 실패 시 Phase별 부분 복구 (last_completed_phase 기반 resume)

---

## 5. 프로젝트 구조

```
app/
├── domain/              # 순수 Python (프레임워크 의존 없음)
│   ├── enums.py         # StrEnum (Weather, Stage, TaskStatus, FileType, OutboxStatus)
│   ├── value_objects.py # VO (VideoId, Temperature, Confidence, StageProgress ...)
│   ├── models.py        # Entity/Model (Selection, AnalyzeTask, OutboxMessage ...)
│   ├── exceptions.py    # 계층형 예외 (DomainError → SelectionParseError → ...)
│   └── ports.py         # ABC Port (Repository, Dispatcher, IdGenerator, Cache, Outbox)
│
├── application/         # 비즈니스 로직 (도메인 조율)
│   ├── analysis_service.py      # 분석 접수 (Outbox 패턴)
│   ├── analyze_task_factory.py  # AnalyzeTask 생성 팩토리
│   ├── pipeline_service.py      # 정제 파이프라인 (청크 단위 진행률)
│   ├── outbox_relay.py          # Outbox 폴링 → 발행
│   ├── task_service.py          # 작업 상태 조회
│   ├── search_service.py        # 검색 (Redis 캐시)
│   ├── rejection_service.py     # 거부 데이터 조회
│   ├── file_loaders.py          # FileLoader 전략 (JSON/CSV + Provider)
│   ├── parsers.py               # Selection 파서 전략 (V1/V2)
│   └── validators.py            # ODD/Label 검증기
│
├── adapter/
│   ├── inbound/
│   │   ├── rest/        # HTTP (routers + schemas + mappers)
│   │   └── worker/      # Celery (pipeline_task + outbox_poller)
│   └── outbound/
│       ├── mysql/       # Entity + Mapper + Repository + QueryBuilder
│       ├── mongodb/     # Document + Mapper + Repository (raw_data, task, outbox)
│       ├── redis/       # Serializer + CacheRepository
│       ├── celery/      # CeleryTaskDispatcher
│       └── identity/    # UUIDv7Generator
│
├── dependencies.py      # DI 팩토리 (FastAPI Depends 체인)
├── worker.py            # Celery 앱 설정 + Beat 스케줄
└── main.py              # FastAPI 앱 + 글로벌 예외 핸들러
```

---

## 6. 설계 결정 (Design Decisions)

### 6-1. 헥사고날 아키텍처 (Port & Adapter)
- domain은 순수 Python 표준 라이브러리만 사용 (FastAPI, SQLAlchemy, PyMongo 의존 없음)
- application은 Port(ABC)만 의존, 구체 구현체는 dependencies.py에서 조립
- adapter는 기술별 패키지 분리 (mysql/, mongodb/, redis/, celery/, identity/)

### 6-2. Value Object
- 원시 타입 대신 의미 있는 타입 (VideoId, Temperature, Confidence, ObjectCount ...)
- 자기 검증 (__post_init__), 변환 로직 캡슐화 (Temperature.from_fahrenheit())
- 비즈니스 판단 메서드 (WiperState.is_raining_likely(), SourcePath.is_raw())

### 6-3. Rich Domain Model
- Selection.is_adverse_weather_likely() — 센서 데이터로 악천후 판단
- OddTag.is_hazardous() — 위험 주행 환경 판단
- Label.is_reliable() — AI 신뢰도 판단
- 도메인 객체가 비즈니스 로직을 가짐 (Anemic Domain 방지)

### 6-4. 전략 패턴
- SelectionParser: V1(flat) / V2(sensor) 스키마 자동 감지 + 정규화
- FileLoader: JSON / CSV 스트리밍 로더 + Provider 확장자 자동 감지
- Parquet 등 새 형식 추가 시 FileLoader 구현 + Provider 등록만으로 확장

### 6-5. QueryBuilder
- SearchQueryBuilder: ODD + Label 동적 필터 조합 (JOIN + 서브쿼리)
- RejectionQueryBuilder: stage + reason 동적 필터
- N+1 방지: IN 절로 OddTag + Labels 일괄 조회 후 메모리 조립

### 6-6. ID 생성
- UUIDv7 사용 (타임스탬프 순서 보장, MongoDB _id 자연 정렬)
- IdGenerator Port → UUIDv7Generator adapter (교체 시 adapter만 변경)

### 6-7. 예외 계층
```
DomainError
├── SelectionParseError → UnknownSchemaError, TemperatureConversionError
├── InvalidOddTagError → InvalidEnumValueError
├── InvalidLabelError → NegativeCountError, FractionalCountError
├── DuplicateRecordError
├── DataNotFoundError
└── InvalidFormatError
```
- RFC 7807 ProblemDetail 에러 응답
- 글로벌 예외 핸들러 (DomainError 400, ValidationError 400, ValueError 400, Exception 500)

### 6-8. 대용량 처리
- CSV 스트리밍: itertools.islice로 5000건씩 읽기 (메모리에 전체 올리지 않음)
- 청크 단위 DB 적재: Repository.save_all()에서 1000건씩 flush
- 실시간 진행률: 청크 처리마다 MongoDB 진행률 업데이트 (0% → 1.5% → 3.1% → ... → 100%)
- 커넥션 풀: SQLAlchemy QueuePool (pool_size=5, max_overflow=10)

### 6-9. Redis AOF
- Redis가 브로커 역할 — AOF 활성화로 메시지 유실 방지
- 프로덕션에서는 Redis Sentinel 또는 RabbitMQ로 고가용성 확보

---

## 7. 데이터 분석 결과

### 발견된 노이즈

| 단계 | 노이즈 | 건수 | 처리 |
|---|---|---|---|
| Selection | 스키마 2종 혼재 (v1/v2) | 98,776 | V1/V2 파서로 정규화 |
| Selection | 온도 단위 불일치 (F vs C) | 69,088 | 섭씨(°C)로 통일 |
| ODD | video_id 중복 태깅 | 40 (20쌍) | 전부 거부 |
| ODD | video_id 제로패딩 | 30 | 정수로 정규화 |
| Label | 음수 obj_count | 10 | 거부 |
| Label | 소수점 obj_count | 15 | 거부 |
| Label | 동일 video_id+class 중복 | 40 (20쌍) | 전부 거부 |

### 처리 결과

| 단계 | 전체 | 적재 | 거부 |
|---|---|---|---|
| Selection | 98,776 | 98,776 | 0 |
| ODD | 96,799 | 96,759 | 40 |
| Label | 322,856 | 322,791 | 65 |
| **완전 통합** | | **95,035** | |

---

## 8. API

| Method | Path | 설명 |
|---|---|---|
| POST | /analyze | 분석 시작 (202 Accepted + task_id) |
| GET | /analyze/{task_id} | 진행률 조회 |
| GET | /rejections | 거부 데이터 조회 (stage, reason 필터) |
| GET | /search | 학습 데이터 검색 (weather, object_class, min_obj_count 등) |

---

## 9. 프로덕션 고려사항

| 현재 | 프로덕션 | 이유 |
|---|---|---|
| Outbox 폴링 (5초) | CDC (MongoDB Change Stream) | 실시간 감지, 지연 밀리초 |
| Redis 단일 | Redis Sentinel 또는 RabbitMQ | 고가용성, 메시지 영속성 |
| SQLite 테스트 | MySQL Testcontainers | 운영 DB와 동일 환경 테스트 |
| 단일 Worker | EKS Pod 스케일 아웃 | Celery worker concurrency 확장 |
| UUIDv7 (라이브러리) | DB 시퀀스 또는 Snowflake | 분산 환경 ID 충돌 방지 |
| docker-compose | Kubernetes (EKS) | 오토스케일링, 롤링 배포 |

---

## 10. AI 활용

- Claude Code를 활용하여 개발
- 멀티 에이전트 시스템 (14개 에이전트 + 6개 스킬)으로 Builder → Reviewer → FIX 루프 자동화
- 상세 프롬프트 기록: CLAUDE.md 참조
