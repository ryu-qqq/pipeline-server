# Python DDD 레퍼런스 프로젝트 리서치 결과

> 조사 일자: 2026-04-09
> 목적: Python 백엔드에서 DDD/Clean Architecture/Hexagonal Architecture 컨벤션 확립을 위한 레퍼런스 수집

---

## 조사한 프로젝트 목록

| # | 프로젝트 | GitHub Stars | 핵심 패턴 |
|---|---|---|---|
| 1 | **cosmicpython/code** | O'Reilly 책 | Repository + UoW + MessageBus + CQRS |
| 2 | **pgorecki/python-ddd** | 1,032 | Modular Monolith + CQRS + Seedwork |
| 3 | **iktakahiro/dddpy** | 704 | Onion Architecture + FastAPI |
| 4 | **qu3vipon/python-ddd** | 453 | Bounded Context + gRPC |
| 5 | **NEONKID/fastapi-ddd-example** | 325 | Protocol 기반 Port + Event-Driven |
| 6 | **szymon6927/hexagonal-architecture-python** | 147 | Hexagonal + MongoDB |

---

## 1. cosmicpython/code (O'Reilly 교과서)

### 디렉토리 구조
```
src/allocation/
├── domain/
│   ├── model.py          # Entity, VO, Aggregate Root
│   ├── commands.py       # Command 정의 (@dataclass)
│   └── events.py         # Domain Event 정의 (@dataclass)
├── adapters/
│   ├── orm.py            # Classical Mapping (도메인 모델과 분리)
│   ├── repository.py     # Abstract + 구현체 (같은 파일)
│   └── notifications.py  # 알림 Abstract + 구현체
├── service_layer/
│   ├── handlers.py       # 함수 기반 Command/Event 핸들러
│   ├── messagebus.py     # MessageBus
│   └── unit_of_work.py   # UoW Abstract + 구현체
├── entrypoints/
│   ├── flask_app.py      # HTTP 진입점
│   └── redis_eventconsumer.py  # 메시지 진입점
├── bootstrap.py          # DI 조립 (inspect.signature 기반)
└── views.py              # CQRS 읽기 모델 (raw SQL)
```

### 핵심 패턴
- **Aggregate + 이벤트 수집**: `Product.events = []`에 이벤트 모으고, UoW가 커밋 시 수거
- **Repository.seen**: 조회/추가된 Aggregate를 추적하여 이벤트 수거에 활용
- **Unit of Work**: Context Manager(`with uow:`)로 트랜잭션 관리, `__exit__`에서 자동 rollback
- **MessageBus**: Command 1:1, Event 1:N 핸들러 매핑
- **DI**: `inspect.signature()` 기반 수동 의존성 주입 (프레임워크 없이)
- **Classical Mapping**: 도메인 모델이 SQLAlchemy를 모름 (orm.py에서 외부 매핑)

### 네이밍 컨벤션
- 추상 클래스: `Abstract` 접두사 (AbstractRepository, AbstractUnitOfWork)
- 구현 클래스: 기술명 접두사 (SqlAlchemyRepository)
- 핸들러: 동사_명사 함수 (allocate, add_batch)
- Command: PascalCase 동사+명사 (Allocate, CreateBatch)
- Event: 과거분사 (Allocated, Deallocated)

### 테스트 구조
```
tests/
├── unit/          # FakeRepository, FakeUoW로 순수 단위 테스트
├── integration/   # 실제 DB (SQLite + PostgreSQL)
└── e2e/           # HTTP 요청으로 전체 흐름
```

---

## 2. pgorecki/python-ddd (Modular Monolith)

### 디렉토리 구조
```
src/
├── config/container.py          # DI 컨테이너 (dependency-injector)
├── seedwork/                    # 공통 빌딩 블록
│   ├── domain/                  # Entity, VO, Rule, Repository 인터페이스
│   ├── application/             # Command, Query, Event 베이스
│   └── infrastructure/          # InMemory/SqlAlchemy Repository
├── modules/
│   ├── catalog/                 # Bounded Context
│   │   ├── domain/entities.py, value_objects.py, rules.py, repositories.py
│   │   ├── application/command/, query/, event/
│   │   └── infrastructure/
│   └── bidding/
└── api/routers/
```

### 핵심 패턴
- **Seedwork**: DDD 빌딩 블록의 공통 추상화 (Entity, AggregateRoot, ValueObject, BusinessRule)
- **CQRS 철저 분리**: Command는 Repository(도메인) 경유, Query는 Session(인프라) 직접 접근
- **Business Rule = Specification 패턴**: Pydantic 모델로 규칙 선언, `is_broken()` 메서드
- **JSONB + Data Mapper**: 도메인 모델과 DB 스키마 완전 분리
- **2단계 DI 컨테이너**: ApplicationContainer(싱글톤) + TransactionContainer(요청 단위)

### 네이밍 컨벤션
- Command: `동사+명사+Command` (CreateListingDraftCommand)
- Query: `Get+대상` (GetAllListings)
- Event: `명사+과거형+Event` (ListingPublishedEvent)
- Rule: `주어+Must/Can+조건` (ListingMustBeDraft)
- Event Handler: `when_이벤트_then_액션` (when_listing_is_published_start_auction)

---

## 3. iktakahiro/dddpy (Onion Architecture)

### 디렉토리 구조
```
dddpy/
├── domain/todo/
│   ├── entities/todo.py          # Rich Domain Model (private 필드 + @property)
│   ├── value_objects/todo_id.py, todo_title.py, todo_status.py
│   ├── repositories/todo_repository.py  # ABC
│   └── exceptions/
├── usecase/todo/
│   ├── create_todo_usecase.py    # ABC + Impl + 팩토리 함수
│   └── ...
├── infrastructure/
│   ├── sqlite/todo/todo_dto.py, todo_repository.py
│   └── di/injection.py
└── presentation/api/todo/
    ├── handlers/
    └── schemas/
```

### 핵심 패턴
- **UseCase ABC + Impl + 팩토리 함수**: 3중 구조
- **Rich Domain Model**: Entity에 private 필드, @property getter, 상태 전이 메서드
- **Value Object**: `@dataclass(frozen=True)` + `__post_init__` 검증
- **DTO 3종 분리**: TodoDTO(DB), TodoSchema(Response), TodoCreateSchema(Request)

### 네이밍 컨벤션
- 인터페이스: 접미사 없음 (TodoRepository)
- 구현체: `Impl` 접미사 (TodoRepositoryImpl)
- 팩토리 함수: `new_` 접두사 (new_todo_repository)
- DI 함수: `get_` 접두사 (get_session)
- 예외: `Error` 접미사 (TodoNotFoundError)

---

## 4. 프로젝트 간 공통 패턴

### 도메인 레이어
| 패턴 | cosmicpython | pgorecki | dddpy | 우리 |
|---|---|---|---|---|
| Entity 정의 | 일반 클래스 | dataclass 상속 | 일반 클래스 (private) | dataclass(frozen) |
| Value Object | @dataclass | @dataclass(frozen) | @dataclass(frozen) | @dataclass(frozen) ✅ |
| Repository 위치 | adapters/ | domain/ | domain/ | domain/ports.py ✅ |
| Repository 타입 | ABC | ABC (Generic) | ABC | ABC ✅ |
| 예외 | 단순 Exception | BusinessRuleValidation | 도메인별 Error | 계층형 Error ✅ |

### 어댑터 레이어
| 패턴 | cosmicpython | pgorecki | dddpy | 우리 |
|---|---|---|---|---|
| DB 매핑 | Classical Mapping | Data Mapper | DTO 변환 | Entity + Mapper ✅ |
| DI 방식 | bootstrap.py 수동 | dependency-injector | FastAPI Depends | Depends ✅ |
| 진입점 분리 | flask_app + redis_consumer | api/routers | presentation/handlers | rest/ + worker/ ✅ |

### 테스트
| 패턴 | cosmicpython | pgorecki | dddpy | 우리 |
|---|---|---|---|---|
| 단위 테스트 | Fake Repository | InMemory Repository | Mock(spec=) | ❌ 미구현 |
| 통합 테스트 | SQLite + PostgreSQL | PostgreSQL | (미구현) | ❌ 미구현 |
| E2E | HTTP 요청 | (미구현) | (미구현) | ❌ 미구현 |

---

## 5. 우리 프로젝트가 추가로 가진 패턴 (레퍼런스에 없는 것)

| 패턴 | 설명 |
|---|---|
| **QueryBuilder** | 동적 검색 조건 조합 (SearchQueryBuilder, RejectionQueryBuilder) |
| **전략 패턴 파서** | V1/V2 스키마 자동 감지 + 변환 |
| **Polyglot Persistence** | MySQL + MongoDB + Redis 3개 저장소 사용 |
| **비동기 파이프라인** | Celery Worker로 정제 분리 |
| **TaskDispatcher Port** | 비동기 작업 발행을 Port로 추상화 |
| **저장소별 패키지 분리** | mysql/, mongodb/, redis/, celery/ |
| **RFC 7807 에러 응답** | ProblemDetail 표준 준수 |
| **MongoDB Document + Mapper** | MySQL Entity/Mapper와 동일 패턴 통일 |
