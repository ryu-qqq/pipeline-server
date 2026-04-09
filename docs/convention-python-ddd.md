# Python DDD 컨벤션

> 참조: Cosmic Python (O'Reilly), pgorecki/python-ddd, iktakahiro/dddpy, qu3vipon/python-ddd
> 원칙: 순수 도메인 격리, 의존성 안쪽 방향, 프레임워크 독립

---

## 0. 레퍼런스 패턴 적용 판단

> 6개 레퍼런스 프로젝트 분석 결과(docs/research-python-ddd.md), 핵심 패턴 3개에 대해 채택/미채택을 결정한다.

### ✅ 채택하지 않음: cosmicpython Unit of Work

| 항목 | 내용 |
|---|---|
| **패턴 요약** | Context Manager(`with uow:`)로 트랜잭션 관리, `__exit__`에서 자동 rollback, Repository.seen으로 이벤트 수거 |
| **미채택 사유** | (1) 이 프로젝트는 FastAPI `Depends(get_db_session)` 제너레이터가 요청 단위 트랜잭션을 이미 관리한다 — commit/rollback/close 책임이 DI 레이어에 있으므로 UoW의 핵심 가치와 중복. (2) Celery Worker는 수동 `session.commit()/rollback()` 패턴을 사용하며, Worker에서 UoW를 도입하면 Celery task 재시도 로직과 트랜잭션 경계가 꼬인다. (3) 이벤트 수거(`Repository.seen`)는 현재 MessageBus가 없으므로 불필요. |
| **대안** | 현행 유지: REST → `get_db_session` 제너레이터, Worker → 명시적 `try/commit/rollback/finally/close` |

### ✅ 채택하지 않음: dddpy UseCase ABC + Impl + 팩토리 함수

| 항목 | 내용 |
|---|---|
| **패턴 요약** | UseCase마다 ABC(인터페이스) + Impl(구현) + `new_xxx()` 팩토리 함수 3중 구조 |
| **미채택 사유** | (1) 서비스 교체 가능성이 없다 — Repository는 MySQL↔InMemory 교체가 있지만, `AnalysisService`를 다른 구현으로 바꿀 일이 없다. (2) 테스트 시 서비스를 Mock할 필요 없음 — 서비스의 의존성(Repository)을 Mock하면 충분. (3) 3중 구조는 Python에서는 보일러플레이트. 파일 수가 3배로 늘어나며 FBD-006(1클래스=1파일 금지) 위반 유발. |
| **대안** | 현행 유지: 구체 Service 클래스 + 생성자 주입. Port 추상화는 Repository/Dispatcher 레벨에서만 적용. |

### ✅ 선택적 채택: pgorecki Business Rule (Specification 패턴)

| 항목 | 내용 |
|---|---|
| **패턴 요약** | `BusinessRule` 베이스 + `is_broken()` 메서드로 도메인 규칙 선언. 예: `ListingMustBeDraft` |
| **현재 상태** | 도메인 불변식은 `__post_init__`(Value Object)과 `Validator` 클래스(application)로 분산 처리 |
| **판단** | 현재 규모에서는 미채택. 단, **향후 도메인 규칙이 5개 이상 조합되는 복잡한 검증**이 생기면 도입을 재검토한다 |
| **채택 조건** | (1) 단일 도메인 모델에 적용할 규칙이 3개 이상 AND (2) 규칙 간 조합(AND/OR)이 필요할 때 |
| **도입 시 위치** | `app/domain/rules.py` — 순수 Python, ABC 기반 |

### 채택한 레퍼런스 패턴 (이미 적용 중)

| 패턴 | 출처 | 현재 적용 상태 |
|---|---|---|
| Repository ABC (Port) | 공통 | `domain/ports.py` ✅ |
| `@dataclass(frozen=True)` 도메인 모델 | dddpy, pgorecki | `domain/models.py`, `domain/value_objects.py` ✅ |
| Mapper (Domain ↔ Entity 분리) | cosmicpython, pgorecki | `outbound/mysql/mappers.py`, `outbound/mongodb/mappers.py` ✅ |
| 전략 패턴 파서 | 자체 | `application/parsers.py` ✅ |
| 진입점 분리 (REST + Worker) | cosmicpython | `inbound/rest/`, `inbound/worker/` ✅ |
| 저장소별 패키지 분리 | 자체 (Polyglot Persistence) | `outbound/mysql/`, `outbound/mongodb/`, `outbound/redis/`, `outbound/celery/` ✅ |
| DI 체인 (FastAPI Depends) | dddpy | `dependencies.py` ✅ |

---

## 1. 레이어 구조

```
app/
├── domain/            # 핵심 비즈니스 규칙 (순수 Python)
├── application/       # 유스케이스 조율 (도메인 조합)
├── adapter/
│   ├── inbound/       # 외부 → 내부 (API 라우터, Worker)
│   │   ├── rest/      # FastAPI 라우터 + Pydantic 스키마
│   │   └── worker/    # Celery 작업 진입점
│   └── outbound/      # 내부 → 외부 (DB, 외부 API)
│       ├── mysql/     # SQLAlchemy Entity + Mapper + Repository
│       ├── mongodb/   # Document + Mapper + Repository
│       ├── redis/     # 캐시 Repository
│       └── celery/    # TaskDispatcher 구현체
├── dependencies.py    # DI 팩토리 함수 (FastAPI Depends 체인)
├── worker.py          # Celery 앱 설정
└── main.py            # FastAPI 앱 진입점 + 글로벌 예외 핸들러
```

---

## 2. 의존성 방향

```
adapter/inbound → application → domain ← adapter/outbound
       (라우터)    (서비스)     (모델)    (리포지토리 구현)

inbound는 application만 알고, application은 domain만 안다.
outbound는 domain의 Port(ABC)를 구현한다.
domain은 아무것도 모른다.
```

### 특수 케이스: Worker 진입점의 DI

Worker(Celery task)는 FastAPI Depends를 사용할 수 없으므로, **task 함수 내에서 직접 의존성을 조립**한다.
이는 `inbound/rest/routers.py`에서 Depends로 주입받는 것과 대칭되는 구조이다.

```python
# adapter/inbound/worker/pipeline_task.py — 허용되는 패턴
@celery_app.task(...)
def process_analysis(self, task_id: str) -> None:
    db = get_mongo_db()
    session = SessionLocal()
    service = PipelineService(
        raw_data_repo=MongoRawDataRepository(db),
        task_repo=MongoTaskRepository(db),
        selection_repo=SqlSelectionRepository(session),
        ...
    )
    service.execute(task_id)
```

**주의**: 구체 구현체를 직접 import하는 것은 **inbound adapter에서만** 허용된다.
application/domain에서는 금지.

---

## 3. Domain 레이어 규칙

### DOM-001: 순수 Python 표준 라이브러리만 허용
```python
# 허용
from dataclasses import dataclass
from enum import StrEnum
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol

# 금지
from fastapi import ...        # 프레임워크 의존
from sqlalchemy import ...     # 인프라 의존
from pydantic import ...       # 외부 라이브러리 의존
```

### DOM-002: 도메인 모델은 dataclass(frozen=True)
```python
@dataclass(frozen=True)
class Selection:
    id: VideoId
    recorded_at: datetime
    temperature: Temperature
    wiper: WiperState
    headlights_on: bool
    source_path: SourcePath
```
- `frozen=True`로 불변성 보장 (Java Record 대응)
- `__post_init__`으로 불변식 검증 가능
- 팩토리 메서드는 `@classmethod`로 정의
- **예외**: 상태가 변경되어야 하는 모델(예: `AnalyzeTask`)은 `@dataclass`(mutable) 허용 — 단, `ports.py` 내 인프라 인접 모델에 한정

### DOM-003: Enum은 StrEnum 사용
```python
class Weather(StrEnum):
    SUNNY = "sunny"
    CLOUDY = "cloudy"
```
- Python 3.11+ `StrEnum` 사용 (구 `str, Enum` 대비 간결)
- 값은 소문자 snake_case (데이터 원본 형식 유지)
- JSON 직렬화 자동 지원

### DOM-004: Port(인터페이스)는 ABC로 정의하고 domain에 위치
```python
# app/domain/ports.py
from abc import ABC, abstractmethod

class SelectionRepository(ABC):
    @abstractmethod
    def save_all(self, selections: list[Selection]) -> None: ...

    @abstractmethod
    def find_by_id(self, selection_id: int) -> Selection | None: ...
```
- 명시적 계약 강제를 위해 ABC 사용 (Protocol 아님)
- 구현체는 adapter/outbound에 위치
- Port 메서드 시그니처에 도메인 모델만 사용 (Entity, DTO 금지)
- **Port별 연관 데이터 모델**(`SearchResult`, `StageProgress`, `AnalyzeTask`)은 해당 Port와 같은 `ports.py`에 배치 가능 — 단, 순수 도메인 모델(`Selection`, `Label` 등)과 혼합하지 않음

### DOM-005: 도메인 예외는 계층형 error_code + message
```python
class DomainError(Exception):
    error_code: str = "DOMAIN_ERROR"
    message: str = "도메인 규칙 위반"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.__class__.message
        super().__init__(self.message)

class SelectionParseError(DomainError):
    error_code = "SELECTION_PARSE_ERROR"

class UnknownSchemaError(SelectionParseError):
    error_code = "UNKNOWN_SCHEMA"
```
- 최상위 `DomainError` → 중간 카테고리(`SelectionParseError`) → 세부 예외(`UnknownSchemaError`)
- 클래스 변수로 `error_code`, `message` 기본값 선언
- `main.py`에서 `DomainError` 하나로 400 응답 처리

### DOM-006: Value Object는 별도 파일

```
domain/
├── __init__.py
├── enums.py          # 모든 StrEnum
├── models.py         # 도메인 모델 (Selection, OddTag, Label, Rejection 등)
├── value_objects.py  # Value Object (VideoId, Temperature, Confidence 등)
├── exceptions.py     # 도메인 예외 계층
└── ports.py          # Repository ABC + Port 연관 데이터 모델
```
- `models.py`는 Value Object를 **사용**하고, `value_objects.py`는 Value Object를 **정의**한다
- Value Object: 단일 값 또는 소수 필드를 감싸고, `__post_init__`에서 불변식을 검증하는 `@dataclass(frozen=True)`
- 파일당 300줄 초과 시 분리 (예: `models/` 디렉토리로 전환)
- 클래스 1개 = 파일 1개는 Java 관례이며 Python에서는 지양

---

## 4. Application 레이어 규칙

### APP-001: 서비스는 Port(ABC)만 의존
```python
class PipelineService:
    def __init__(
        self,
        raw_data_repo: RawDataRepository,     # ABC (Port)
        task_repo: TaskRepository,             # ABC (Port)
        selection_repo: SelectionRepository,   # ABC (Port)
        odd_tag_repo: OddTagRepository,        # ABC (Port)
        label_repo: LabelRepository,           # ABC (Port)
        rejection_repo: RejectionRepository,   # ABC (Port)
    ) -> None:
        ...
```
- 생성자 주입 (Java @Autowired 생성자 주입 대응)
- 구체 구현체(SqlSelectionRepository) 직접 import 금지
- **ABC 추가 금지**: 서비스 자체에 ABC를 만들지 않는다 (dddpy UseCase ABC 미채택)

### APP-002: application에서 허용하는 import
```python
# 허용
from app.domain.models import Selection
from app.domain.enums import Weather
from app.domain.ports import SelectionRepository
from app.domain.exceptions import DomainError

# 허용 (표준 라이브러리)
from datetime import datetime
from pathlib import Path
import json, csv, logging, uuid

# 금지
from app.adapter.outbound.repositories import SqlSelectionRepository  # 구체 구현체
from fastapi import ...          # 프레임워크
from sqlalchemy import ...       # 인프라
```

### APP-003: 전략 패턴은 application에 위치
```python
# app/application/parsers.py
class SelectionParser(ABC):
    @abstractmethod
    def parse(self, raw: dict) -> Selection: ...

class V1SelectionParser(SelectionParser): ...
class V2SelectionParser(SelectionParser): ...

def detect_parser(raw: dict) -> SelectionParser:
    """스키마를 감지하여 적절한 파서를 반환한다."""
    ...
```
- 파서, 검증기 등 비즈니스 전략은 application 레이어
- domain의 순수 모델과 분리
- 팩토리 함수(`detect_parser`)는 전략 클래스와 같은 파일에 배치

### APP-004: 검증기(Validator)는 application에 위치
```python
# app/application/validators.py
class OddValidator:
    def validate_batch(self, rows: list[dict], valid_video_ids: set[int]) -> tuple[list[OddTag], list[Rejection]]:
        ...

class LabelValidator:
    def validate_batch(self, rows: list[dict], valid_video_ids: set[int]) -> tuple[list[Label], list[Rejection]]:
        ...
```
- raw dict → 도메인 모델 변환 + 거부 분류 로직
- Value Object의 `__post_init__` 검증과는 역할이 다름: Validator는 **외부 데이터 정제**, Value Object는 **불변식 보장**
- 향후 규칙이 복잡해지면 pgorecki의 BusinessRule 패턴 도입을 재검토 (섹션 0 참조)

### APP-005: 파일 구조
```
application/
├── __init__.py
├── analysis_service.py    # 분석 접수 (Command — 파일 적재 + 작업 발행)
├── pipeline_service.py    # 정제 파이프라인 (Command — 정제 + MySQL 적재)
├── task_service.py        # 작업 상태 조회 (Query)
├── search_service.py      # 학습 데이터 검색 (Query)
├── rejection_service.py   # 거부 데이터 조회 (Query)
├── parsers.py             # 데이터 파싱 전략 (V1Parser, V2Parser)
└── validators.py          # 검증 규칙 (OddValidator, LabelValidator)
```
- Command 서비스(상태 변경)와 Query 서비스(조회 전용) 분리
- 서비스 파일명은 `{기능}_service.py` 형식

---

## 5. Adapter 레이어 규칙

### ADP-IN-001: REST 라우터는 UseCase(서비스)만 의존
```python
# app/adapter/inbound/rest/routers.py
@router.post("/analyze")
def analyze(service: AnalysisService = Depends(get_analysis_service)):
    task_id = service.submit()
    return JSONResponse(...)
```
- 라우터에 비즈니스 로직 금지
- Pydantic 스키마 ↔ 도메인 모델 변환은 **Mapper 클래스**로 위임

### ADP-IN-002: REST 레이어 3파일 구조
```
adapter/inbound/rest/
├── routers.py    # FastAPI 라우터 (엔드포인트 정의)
├── schemas.py    # Pydantic Request/Response DTO
└── mappers.py    # Schema ↔ Domain 변환기
```
- Pydantic은 `adapter/inbound/rest/`에서만 사용
- domain에서 Pydantic import 금지
- **Mapper 역할**: `to_domain()` (Request → 도메인 모델), `from_domain()` (도메인 모델 → Response)

### ADP-IN-003: Worker 진입점은 adapter/inbound/worker에 위치
```
adapter/inbound/worker/
└── pipeline_task.py  # Celery task 함수 (DI 조립 + 서비스 위임)
```
- Celery task 함수는 **inbound adapter**이다 (외부 메시지 → 내부 서비스)
- 비즈니스 로직은 서비스에 위임
- DI 조립은 task 함수 내에서 직접 수행 (Depends 미사용)

### ADP-OUT-001: Repository 구현체는 Port(ABC)를 상속
```python
class SqlSelectionRepository(SelectionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_all(self, selections: list[Selection]) -> None:
        entities = [SelectionMapper.to_entity(s) for s in selections]
        self._session.add_all(entities)
```

### ADP-OUT-002: Entity/Document와 Domain 모델은 분리, Mapper로 변환

**MySQL 패턴**:
```python
# outbound/mysql/entities.py — SQLAlchemy 모델 (DB 관심사)
class SelectionEntity(Base):
    __tablename__ = "selections"

# outbound/mysql/mappers.py — 변환기
class SelectionMapper:
    @staticmethod
    def to_entity(domain: Selection) -> SelectionEntity: ...
    @staticmethod
    def to_domain(entity: SelectionEntity) -> Selection: ...
```

**MongoDB 패턴** (동일 구조):
```python
# outbound/mongodb/documents.py — MongoDB Document (DB 관심사)
@dataclass
class RawDataDocument:
    task_id: str
    source: str
    data: dict

# outbound/mongodb/mappers.py — 변환기
class RawDataDocumentMapper:
    @staticmethod
    def to_document(task_id: str, source: str, data: dict) -> dict: ...
    @staticmethod
    def to_domain(doc: dict) -> dict: ...
```

### ADP-OUT-003: 저장소별 패키지 구조
```
adapter/outbound/
├── mysql/
│   ├── database.py       # 엔진, 세션, Base 설정
│   ├── entities.py       # SQLAlchemy 모델
│   ├── mappers.py        # Domain ↔ Entity 변환
│   ├── repositories.py   # Repository 구현체
│   └── query_builder.py  # 동적 쿼리 조합 (SearchQueryBuilder 등)
├── mongodb/
│   ├── client.py         # MongoDB 연결 + 인덱스 관리
│   ├── documents.py      # Document 정의
│   ├── mappers.py        # Domain ↔ Document 변환
│   └── repositories.py   # Repository 구현체
├── redis/
│   ├── client.py         # Redis 연결
│   ├── serializer.py     # JSON 직렬화
│   └── repositories.py   # CacheRepository 구현체
└── celery/
    └── dispatcher.py     # TaskDispatcher 구현체
```
- 저장소 기술별로 패키지를 분리한다 (Polyglot Persistence 대응)
- 각 패키지 내부 구조는 통일: `{연결설정}` + `{모델}` + `{매퍼}` + `{리포지토리}`

### ADP-OUT-004: QueryBuilder는 outbound에 위치
```python
# outbound/mysql/query_builder.py
class SearchQueryBuilder:
    def __init__(self, criteria: SearchCriteria) -> None: ...
    def build_query(self) -> Select: ...
    def build_count_query(self) -> Select: ...
```
- 동적 WHERE 조건 조합은 인프라 관심사이므로 outbound에 위치
- criteria(도메인 모델)를 받아 SQLAlchemy Select를 반환

---

## 6. DI (의존성 주입) 규칙

### DI-001: FastAPI Depends()로 DI 체인 구성
```python
# app/dependencies.py
def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_selection_repo(session: Session = Depends(get_db_session)) -> SelectionRepository:
    return SqlSelectionRepository(session)

def get_analysis_service(
    raw_data_repo: RawDataRepository = Depends(get_raw_data_repo),
    task_repo: TaskRepository = Depends(get_task_repo),
    task_dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> AnalysisService:
    return AnalysisService(...)
```
- DI 팩토리 함수는 `dependencies.py` 한 파일에 모음
- 반환 타입은 ABC(Port) 타입으로 명시
- Session 관리(commit/rollback)는 `get_db_session` 제너레이터에 집중 — UoW 패턴 미사용

### DI-002: DI 파일에서만 구체 구현체 import 허용
```python
# dependencies.py — 유일하게 구체 구현체를 아는 곳 (REST 경로)
from app.adapter.outbound.mysql.repositories import SqlSelectionRepository
from app.adapter.outbound.mongodb.repositories import MongoRawDataRepository
```
- `dependencies.py`와 `adapter/inbound/worker/` — 이 두 곳에서만 구체 구현체를 import한다
- application, domain에서는 절대 import 금지

---

## 7. 테스트 규칙

### TST-001: 레이어별 독립 테스트
```
tests/
├── conftest.py               # 공통 fixture
├── domain/
│   └── test_models.py        # 도메인 단위 테스트 (외부 의존 없음)
│   └── test_value_objects.py # Value Object 불변식 테스트
├── application/
│   ├── test_parsers.py       # 파서 단위 테스트
│   ├── test_validators.py    # 검증기 단위 테스트
│   └── test_services.py      # Mock Repository로 서비스 테스트
└── adapter/
    ├── test_routers.py       # TestClient로 API 통합 테스트
    └── test_repositories.py  # SQLite in-memory로 DB 통합 테스트
```

### TST-002: domain 테스트에는 Mock/DB 없음
```python
def test_selection_frozen():
    s = Selection(id=VideoId(1), ...)
    with pytest.raises(AttributeError):
        s.id = VideoId(999)

def test_video_id_rejects_zero():
    with pytest.raises(InvalidFormatError):
        VideoId(0)
```

### TST-003: application 테스트는 Mock Repository
```python
from unittest.mock import MagicMock

def test_pipeline_service():
    mock_repo = MagicMock(spec=SelectionRepository)
    service = PipelineService(selection_repo=mock_repo, ...)
    service.execute(task_id)
    mock_repo.save_all.assert_called_once()
```

### TST-004: adapter 테스트는 실제 DB (SQLite in-memory)
```python
@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
```

---

## 8. 네이밍 컨벤션

### 파이썬 표준 (PEP 8)
| 대상 | 규칙 | 예시 |
|---|---|---|
| 파일명 | snake_case | `selection_parser.py` |
| 클래스 | PascalCase | `SelectionParser` |
| 함수/메서드 | snake_case | `find_by_id` |
| 상수 | UPPER_SNAKE | `MAX_CHUNK_SIZE` |
| private | 언더스코어 prefix | `self._session` |
| 변수 | snake_case | `video_id` |

### 프로젝트 네이밍
| 대상 | 규칙 | 예시 |
|---|---|---|
| Repository ABC | `{Entity}Repository` | `SelectionRepository` |
| MySQL Repository 구현체 | `Sql{Entity}Repository` | `SqlSelectionRepository` |
| MongoDB Repository 구현체 | `Mongo{Entity}Repository` | `MongoRawDataRepository` |
| Redis Repository 구현체 | `Redis{기능}Repository` | `RedisCacheRepository` |
| Entity (SQLAlchemy) | `{Entity}Entity` | `SelectionEntity` |
| Document (MongoDB) | `{Entity}Document` | `RawDataDocument` |
| Mapper | `{Entity}Mapper` | `SelectionMapper` |
| Service | `{기능}Service` | `AnalysisService`, `PipelineService` |
| Validator | `{Entity}Validator` | `OddValidator`, `LabelValidator` |
| Parser | `{버전}{Entity}Parser` | `V1SelectionParser` |
| Pydantic DTO | `{기능}Request/Response` | `RejectionSearchRequest` |
| Enum | PascalCase (값은 snake_case) | `Weather.SUNNY = "sunny"` |
| Value Object | PascalCase (단일 값 감싼 모델) | `VideoId`, `Temperature` |
| QueryBuilder | `{Entity}QueryBuilder` | `SearchQueryBuilder` |
| Dispatcher | `{기술}TaskDispatcher` | `CeleryTaskDispatcher` |
| 예외 (도메인) | `{카테고리}Error` | `SelectionParseError` |
| REST Mapper | `{Entity}ResponseMapper` 등 | `RejectionResponseMapper` |
| DI 팩토리 함수 | `get_{대상}` | `get_selection_repo` |

---

## 9. 금지 사항

| 코드 | 규칙 | 이유 |
|---|---|---|
| **FBD-001** | domain에서 외부 라이브러리 import 금지 | 도메인 순수성 |
| **FBD-002** | application에서 구체 구현체 import 금지 | DIP 위반 |
| **FBD-003** | adapter/inbound(라우터)에 비즈니스 로직 금지 | Thin Layer 원칙 |
| **FBD-004** | SQLAlchemy 관계 어노테이션 사용 금지 | FK ID 전략으로 N+1 차단 |
| **FBD-005** | domain 모델에 Pydantic BaseModel 사용 금지 | 프레임워크 의존 |
| **FBD-006** | 클래스 1개 = 파일 1개 구조 금지 | Java 관례. Python은 모듈 단위 |
| **FBD-007** | Service에 ABC 추상화 금지 | 교체 불필요 (UseCase ABC 미채택) |
| **FBD-008** | application/domain에서 구체 구현체 import 금지 | DI 레이어에서만 조립 |

---

## 10. 현재 코드 위반 사항 리포트

> 기준: `app/` 디렉토리 전수 조사 (2026-04-09)

### 🔴 위반 (수정 필요)

| # | 위치 | 위반 규칙 | 설명 | 권장 조치 |
|---|---|---|---|---|
| V-01 | `domain/ports.py:103` | DOM-002 | `AnalyzeTask`가 `@dataclass`(mutable)로 정의됨. `status`, `result`, `error` 등 필드가 변경 가능. 그러나 실제로 application에서 직접 mutate하지 않고 Repository가 DB에서 읽어온 값을 세팅하므로, **frozen=True + 새 인스턴스 반환** 패턴이 더 적절 | `@dataclass(frozen=True)` 전환. 상태 변경은 `TaskRepository.update_status()` 등 Port 메서드로만 수행하므로 mutable일 필요 없음 |
| V-02 | `domain/ports.py:71-116` | DOM-006 | `SearchResult`, `StageProgress`, `AnalyzeTask` — Port 연관 데이터 모델이 ports.py에 혼합 정의됨. 모델이 3개 이상이므로 별도 파일 분리 검토 필요 | `domain/ports.py`에 유지하되, 파일 상단에 `# === Port 연관 데이터 모델 ===` 섹션 주석으로 구분. 또는 `domain/task_models.py`로 분리 |
| V-03 | `adapter/inbound/rest/schemas.py:7-14` | (경미) | `schemas.py`에서 `app.domain.enums` 직접 import. 컨벤션상 허용 범위이나, Request DTO가 도메인 Enum 타입을 직접 사용하면 **도메인 Enum 변경 시 API 스키마가 깨진다** | 현행 유지 가능 (실용적 타협). 향후 API 안정성이 중요해지면 별도 Enum 사용 검토 |

### 🟡 개선 권장 (긴급하지 않음)

| # | 위치 | 설명 | 권장 조치 |
|---|---|---|---|
| I-01 | `adapter/inbound/worker/pipeline_task.py:3-13` | Worker에서 모든 구체 구현체를 직접 import. 허용된 패턴이지만 `dependencies.py`와 중복 조립 코드 발생 | Worker 전용 DI 함수를 `dependencies.py`에 추가하거나 현행 유지 (trade-off 판단) |
| I-02 | `domain/ports.py:108` | `AnalyzeTask.status`가 `str` 타입. `"pending"`, `"processing"` 등 매직 스트링 사용 | `TaskStatus(StrEnum)` 도입하여 `domain/enums.py`에 추가 |
| I-03 | `domain/ports.py:150` | `TaskRepository.update_progress`의 `stage` 파라미터가 `str`. `"selection"`, `"odd_tagging"` 등 매직 스트링 | 기존 `Stage(StrEnum)`을 활용하도록 시그니처 변경 |
| I-04 | 전체 | 테스트 미구현 (TST-001~004) | 다음 단계에서 테스트 작성 필요 |
