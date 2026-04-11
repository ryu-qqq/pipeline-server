# Pipeline Server 프로젝트 CLAUDE.md

## 프로젝트 개요
자율주행 영상 데이터의 **정제 → 통합 → 분석 API**를 제공하는 파이프라인 서버.
3개 원본 파일(Selection, ODD Tagging, Auto Labeling)을 읽어 데이터 품질을 검증하고, 정제된 학습 데이터셋을 ML 엔지니어가 다양한 조건으로 검색할 수 있도록 한다.

## 언어 설정
- 모든 응답, 코드 주석, 커밋 메시지, 문서는 **한국어**로 작성한다.
- 코드 내 변수명/메서드명 등 프로그래밍 식별자는 영어를 유지한다.

## 기술 스택
| 항목 | 선택 |
|------|------|
| Language | Python 3.12 |
| Framework | FastAPI |
| Build | Docker Compose |
| Database | MySQL 8.0 (정제 데이터 저장, 복합 검색) |
| Document Store | MongoDB 7.0 Replica Set (원본 보관, 작업 상태, Outbox) |
| Cache/Broker | Redis 7.0 (Celery 브로커 + 검색 캐시) |
| Async Worker | Celery + Beat (비동기 정제 파이프라인 + Outbox 폴링) |
| ORM | SQLAlchemy (ORM + Core 혼용, INSERT IGNORE 배치) |
| Test | pytest + testcontainers (MySQL, MongoDB, Redis) |

---

## 아키텍처 — DDD + Hexagonal 단일 모듈

```
pipeline-server/
├── app/
│   ├── domain/                          # 순수 Python — 외부 라이브러리 의존 없음
│   │   ├── models.py                    # frozen dataclass (Selection, OddTag, Label, Rejection, AnalyzeTask, OutboxMessage)
│   │   ├── value_objects.py             # VideoId, Temperature, Confidence, ObjectCount, WiperState, SourcePath, StageProgress
│   │   ├── enums.py                     # Weather, TimeOfDay, RoadSurface, ObjectClass, Stage, TaskStatus, RejectionReason
│   │   ├── ports.py                     # Repository ABC (SelectionRepository, TaskRepository, CacheRepository 등)
│   │   └── exceptions.py               # 도메인 예외 계층
│   ├── application/                     # 서비스, Refiner, PhaseRunner, FileLoader
│   │   ├── analysis_service.py          # POST /analyze 접수 (Command)
│   │   ├── pipeline_service.py          # 정제 파이프라인 실행 (Worker에서 호출)
│   │   ├── outbox_relay_service.py      # Outbox 폴링 → Worker 발행
│   │   ├── selection_refiner.py         # Selection 정제 (V1/V2 스키마 자동 감지)
│   │   ├── odd_tag_refiner.py           # ODD 태깅 정제
│   │   ├── label_refiner.py             # Auto Labeling 정제
│   │   ├── phase_runners.py             # PhaseRunner + PhaseRunnerProvider (Strategy 패턴)
│   │   ├── data_ingestor.py             # 원본 파일 → MongoDB 적재
│   │   ├── file_loaders.py              # JSON/CSV 파일 로더 (FileLoaderProvider)
│   │   ├── task_read_service.py         # 작업 상태 조회 (Query)
│   │   ├── data_read_service.py         # 학습 데이터 검색 (Query)
│   │   ├── rejection_read_service.py    # 거부 데이터 조회 (Query)
│   │   └── decorators.py               # @transactional 데코레이터
│   ├── adapter/
│   │   ├── inbound/
│   │   │   ├── rest/                    # FastAPI Router, Pydantic Schema, Mapper
│   │   │   └── worker/                  # Celery Task (pipeline_task, outbox_poller_task)
│   │   └── outbound/
│   │       ├── mysql/                   # SQLAlchemy Entity, Mapper, Repository, QueryBuilder
│   │       ├── mongodb/                 # PyMongo Document, Mapper, Repository, Transaction
│   │       ├── redis/                   # Redis 캐시 Repository, Serializer
│   │       ├── celery/                  # CeleryTaskDispatcher
│   │       └── identity/               # UUIDv7 Generator
│   ├── main.py                          # FastAPI 앱 진입점
│   ├── worker.py                        # Celery Worker 진입점
│   ├── rest_dependencies.py             # REST DI 조립
│   └── worker_dependencies.py           # Worker DI 조립
├── tests/
│   ├── domain/                          # 도메인 단위 테스트 (순수 Python)
│   ├── application/                     # Application 단위 테스트 (Mock Repository)
│   ├── adapter/                         # Adapter 단위 테스트 (SQLite in-memory + TestClient)
│   └── integration/                     # E2E 통합 테스트 (testcontainers)
├── notebooks/
│   └── data-analysis.ipynb              # 데이터 탐색 노트북
└── docs/
    ├── data-analysis.md                 # 데이터 분석 결과 정리
    ├── data-model.md                    # ERD, 인덱스 설계
    ├── architecture.md                  # 아키텍처 설계 문서
    └── testing-strategy.md              # 테스트 전략
```

### 설계 원칙
1. **Domain은 순수 Python** — 외부 라이브러리 import 금지
2. **frozen dataclass + replace** — 도메인 모델 불변 설계, 상태 전이 시 새 인스턴스 생성
3. **Port는 Domain에** — ABC로 정의, Adapter에서 구현
4. **의존성 방향** — Inbound Adapter → Application → Domain ← Outbound Adapter
5. **DI 조립은 루트에** — `rest_dependencies.py`, `worker_dependencies.py`에서 구현체 주입
6. **Transactional Outbox** — MongoDB 트랜잭션으로 Task + 이벤트 원자적 저장
7. **INSERT IGNORE** — 중복 처리를 DB에 위임, resume 시 멱등성 보장

---

## 에이전트 목록 (`.claude/agents/`)

| 분류 | 에이전트 | 핵심 책임 |
|------|---------|-----------|
| 기획 | product-owner | 요구사항 분석, 백로그 관리 |
| 설계 | project-lead | 아키텍처 결정, 컨벤션 정의 |
| QA/PM | project-manager | 산출물 감사, 완성도 검증 |
| 컨벤션 | convention-guardian | Python DDD 컨벤션 검증 |
| 도메인 개발 | domain-builder | 도메인 모델 코드 생성 |
| 서비스 개발 | service-builder | Application 레이어 코드 생성 |
| 인프라 개발 | infra-builder | REST, Redis, Celery, Docker 코드 생성 |
| 영속성 개발 | persistence-builder | MySQL Entity, MongoDB Document, Mapper, Repository |
| 코드 리뷰 | code-reviewer | 전 레이어 설계 적절성 리뷰 |
| 단위 테스트 | unit-test-designer | Domain/Application 단위 테스트 설계 |
| 통합 테스트 | integration-test-designer | Adapter 통합 테스트 설계 |
| E2E 테스트 | e2e-test-designer | Testcontainers 기반 E2E 테스트 설계 |
| 파이프라인 | pipeline-orchestrator | 빌드 파이프라인 실행 엔진 |
| 테스트 하네스 | test-harness-orchestrator | 테스트 파이프라인 실행 엔진 |
| 채용 | agent-recruiter | 새 에이전트 생성/관리 |

## 스킬 목록 (`.claude/skills/`)

| 스킬 | 용도 |
|------|------|
| pipeline | 전체 빌드 파이프라인 실행 |
| domain-harness | 도메인 레이어 빌드 → 린트 → 리뷰 → 테스트 |
| service-harness | Application 레이어 빌드 → 리뷰 → 테스트 |
| persistence-harness | 영속성 레이어 빌드 → 리뷰 → 테스트 |
| infra-harness | 인프라 레이어 빌드 → 리뷰 → 테스트 |
| test-harness | 테스트 분석 → 시나리오 설계 → 생성 → 실행 |

### 하네스 파이프라인 흐름

각 레이어마다 하네스가 있어서 아래 사이클을 자동으로 순환한다:

```
빌더가 코드 생성 → 리뷰어가 컨벤션/구조 검증 → PASS or FIX-REQUEST
  → FIX 시 빌더가 수정 (최대 2회) → 테스트 설계/실행
  → FIX 2회 초과 시 project-lead 에스컬레이션
```

---

## API 구조

```
POST   /analyze              # 분석 요청 → 202 반환, 비동기 정제 시작
GET    /analyze/{task_id}     # 진행 상태 조회
GET    /data                  # 학습 데이터 검색 (복합 조건 필터링, offset + cursor 페이징)
GET    /rejections            # 거부 데이터 조회 (stage + reason 필터링)
```

## 테스트 전략
1. **도메인 단위 테스트**: 순수 Python, VO/Model 비즈니스 로직 검증
2. **Application 단위 테스트**: Mock Repository, 서비스 흐름 검증
3. **Adapter 단위 테스트**: SQLite in-memory + TestClient, 쿼리/API 검증
4. **E2E 통합 테스트**: testcontainers(MySQL, MongoDB, Redis), 전체 파이프라인 검증

## 커밋 컨벤션
한국어로 작성하며, 무엇을 왜 변경했는지 간결하게 기술한다.

## 주요 참조 문서

| 문서 | 경로 | 설명 |
|------|------|------|
| 데이터 분석 | `docs/data-analysis.md` | V1/V2 스키마 비율, 노이즈 패턴, 거부 사유 도출 |
| 데이터 모델 | `docs/data-model.md` | ERD, 인덱스 설계, MongoDB 컬렉션 구조 |
| 아키텍처 | `docs/architecture.md` | DDD + Hexagonal, 데이터 흐름, Polyglot Persistence |
| 테스트 전략 | `docs/testing-strategy.md` | 테스트 피라미드, 레이어별 전략 |
| 데이터 탐색 | `notebooks/data-analysis.ipynb` | Jupyter Notebook 시각화 분석 |
