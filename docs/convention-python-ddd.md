# Python DDD 컨벤션

> 참조: Cosmic Python (O'Reilly), pgorecki/python-ddd, iktakahiro/dddpy, qu3vipon/python-ddd
> 원칙: 순수 도메인 격리, 의존성 안쪽 방향, 프레임워크 독립

---

## 1. 레이어 구조

```
app/
├── domain/            # 핵심 비즈니스 규칙 (순수 Python)
├── application/       # 유스케이스 조율 (도메인 조합)
├── adapter/
│   ├── inbound/       # 외부 → 내부 (API 라우터, CLI)
│   └── outbound/      # 내부 → 외부 (DB, 외부 API)
└── main.py            # 앱 진입점 + DI 조립
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

---

## 3. Domain 레이어 규칙

### DOM-001: 순수 Python 표준 라이브러리만 허용
```python
# 허용
from dataclasses import dataclass
from enum import Enum
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
    id: int
    recorded_at: datetime
    temperature_celsius: float
```
- `frozen=True`로 불변성 보장 (Java Record 대응)
- `__post_init__`으로 불변식 검증 가능
- 팩토리 메서드는 `@classmethod`로 정의

### DOM-003: Enum은 str 상속
```python
class Weather(str, Enum):
    SUNNY = "sunny"
    CLOUDY = "cloudy"
```
- `str` 상속으로 JSON 직렬화 자동 지원
- 값은 소문자 snake_case (데이터 원본 형식 유지)

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

### DOM-005: 도메인 예외는 error_code + message
```python
class DomainException(Exception):
    def __init__(self, error_code: str, message: str) -> None:
        self.error_code = error_code
        self.message = message
```

### DOM-006: 파일 구조
```
domain/
├── __init__.py
├── enums.py          # 모든 Enum (관련 Enum을 한 파일에)
├── models.py         # 모든 dataclass (300줄 이하면 한 파일)
├── exceptions.py     # 도메인 예외
└── ports.py          # 모든 Repository ABC (Port-Out)
```
- 파일당 300줄 초과 시 분리 (models/ 디렉토리로 전환)
- 클래스 1개 = 파일 1개는 Java 관례이며 Python에서는 지양

---

## 4. Application 레이어 규칙

### APP-001: 서비스는 Port(ABC)만 의존
```python
class AnalysisService:
    def __init__(
        self,
        selection_repo: SelectionRepository,  # ABC (Port)
        rejection_repo: RejectionRepository,  # ABC (Port)
    ) -> None:
        self._selection_repo = selection_repo
        self._rejection_repo = rejection_repo
```
- 생성자 주입 (Java @Autowired 생성자 주입 대응)
- 구체 구현체(SqlSelectionRepository) 직접 import 금지

### APP-002: application에서 허용하는 import
```python
# 허용
from app.domain.models import Selection
from app.domain.enums import Weather
from app.domain.ports import SelectionRepository
from app.domain.exceptions import DomainException

# 허용 (표준 라이브러리)
from datetime import datetime
from pathlib import Path

# 금지
from app.adapter.outbound.repositories import SqlSelectionRepository  # 구체 구현체
from fastapi import ...          # 프레임워크
from sqlalchemy import ...       # 인프라
```

### APP-003: 전략 패턴은 application에 위치
```python
# app/application/parsers.py
from abc import ABC, abstractmethod

class SelectionParser(ABC):
    @abstractmethod
    def parse(self, raw: dict) -> Selection: ...

class V1SelectionParser(SelectionParser): ...
class V2SelectionParser(SelectionParser): ...
```
- 파서, 검증기 등 비즈니스 전략은 application 레이어
- domain의 순수 모델과 분리

### APP-004: 파일 구조
```
application/
├── __init__.py
├── services.py       # UseCase 구현 (AnalysisService, SearchService)
├── parsers.py        # 데이터 파싱 전략 (V1Parser, V2Parser)
└── validators.py     # 검증 규칙 (OddValidator, LabelValidator)
```

---

## 5. Adapter 레이어 규칙

### ADP-IN-001: 라우터는 UseCase(서비스)만 의존
```python
# app/adapter/inbound/routers.py
@router.post("/analyze")
def analyze(service: AnalysisService = Depends(get_analysis_service)):
    return service.analyze()
```
- 라우터에 비즈니스 로직 금지
- Pydantic 스키마 ↔ 도메인 모델 변환만 수행

### ADP-IN-002: API DTO는 Pydantic BaseModel
```python
# app/adapter/inbound/schemas.py
from pydantic import BaseModel

class AnalysisResponse(BaseModel):
    total: int
    loaded: int
    rejected: int
```
- Pydantic은 adapter/inbound에서만 사용
- domain에서 Pydantic import 금지

### ADP-OUT-001: Repository 구현체는 Port(ABC)를 상속
```python
# app/adapter/outbound/repositories.py
class SqlSelectionRepository(SelectionRepository):  # ABC 상속
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_all(self, selections: list[Selection]) -> None:
        entities = [SelectionMapper.to_entity(s) for s in selections]
        self._session.add_all(entities)
```

### ADP-OUT-002: Entity와 Domain 모델은 분리, Mapper로 변환
```python
# app/adapter/outbound/entities.py — SQLAlchemy 모델 (DB 관심사)
class SelectionEntity(Base):
    __tablename__ = "selections"
    id: Mapped[int] = mapped_column(primary_key=True)

# app/adapter/outbound/mappers.py — 변환기
class SelectionMapper:
    @staticmethod
    def to_entity(domain: Selection) -> SelectionEntity: ...

    @staticmethod
    def to_domain(entity: SelectionEntity) -> Selection: ...
```
- SQLAlchemy 모델은 adapter/outbound에만 존재
- domain은 SQLAlchemy를 모름

### ADP-OUT-003: 파일 구조
```
adapter/
├── inbound/
│   ├── __init__.py
│   ├── routers.py        # FastAPI 라우터
│   └── schemas.py        # Pydantic Request/Response DTO
└── outbound/
    ├── __init__.py
    ├── database.py       # 엔진, 세션, Base 설정
    ├── entities.py       # SQLAlchemy 모델
    ├── mappers.py        # Domain ↔ Entity 변환
    └── repositories.py   # Repository 구현체
```

---

## 6. DI (의존성 주입) 규칙

### DI-001: FastAPI Depends()로 DI 체인 구성
```python
# app/dependencies.py
def get_db_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_selection_repo(
    session: Session = Depends(get_db_session),
) -> SelectionRepository:
    return SqlSelectionRepository(session)

def get_analysis_service(
    selection_repo: SelectionRepository = Depends(get_selection_repo),
) -> AnalysisService:
    return AnalysisService(selection_repo=selection_repo)
```
- DI 팩토리 함수는 `dependencies.py` 한 파일에 모음
- 반환 타입은 ABC(Port) 타입으로 명시

---

## 7. 테스트 규칙

### TST-001: 레이어별 독립 테스트
```
tests/
├── conftest.py               # 공통 fixture
├── domain/
│   └── test_models.py        # 도메인 단위 테스트 (외부 의존 없음)
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
# domain 테스트 — 순수 Python만
def test_selection_frozen():
    s = Selection(id=1, ...)
    with pytest.raises(AttributeError):
        s.id = 999
```

### TST-003: application 테스트는 Mock Repository
```python
from unittest.mock import MagicMock

def test_analysis_service():
    mock_repo = MagicMock(spec=SelectionRepository)
    service = AnalysisService(selection_repo=mock_repo)
    service.analyze()
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
| Repository 구현체 | `Sql{Entity}Repository` | `SqlSelectionRepository` |
| Entity (SQLAlchemy) | `{Entity}Entity` | `SelectionEntity` |
| Mapper | `{Entity}Mapper` | `SelectionMapper` |
| Service | `{기능}Service` | `AnalysisService` |
| Pydantic DTO | `{기능}Request/Response` | `RejectionResponse` |
| Enum | PascalCase (값은 snake_case) | `Weather.SUNNY = "sunny"` |

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
